import csv
import io
from datetime import date, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.statements import insert
from app.models import Business, BusinessMembership, Expense, Product, Sale
from app.schemas.analytics import DemoLoad, Period
from app.schemas.imports import BusinessRead
from app.services.import_parser import parse_file
from app.services.import_store import confirm_import

DEMO_VERSION = "taraz-cafe-v1"
DEMO_BUSINESS_ID = uuid5(NAMESPACE_URL, "profitleak/demo/" + DEMO_VERSION)
DEMO_START = date(2026, 7, 4)
DEMO_END = DEMO_START + timedelta(days=89)


def csv_bytes(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build_demo_files() -> dict[str, bytes]:
    """Stable 90 day synthetic dataset with three evidence based detector scenarios."""
    sales = []
    expenses = []
    for offset in range(90):
        day = (DEMO_START + timedelta(days=offset)).isoformat()
        sales.extend(
            [
                [day, "P001", "Кофе", 25, 1200, 450 if offset < 60 else 900],
                [day, "P002", "Чай", 18, 700, 250],
                [day, "P003", "Сэндвич", 10, 1800, 800],
            ]
        )
        expenses.extend(
            [
                [day, "Packaging", "Упаковка", 1000 if offset < 60 else 1500],
                [day, "Wages", "Оплата труда", 1500],
                [day, "Utilities", "Коммунальные расходы", 500],
            ]
        )
        if offset in (0, 30, 60):
            expenses.append([day, "Rent", "Аренда", 150000])
    # Preserve this identical row so POSSIBLE_DUPLICATE can reference both source rows.
    expenses.append([DEMO_END.isoformat(), "Packaging", "Упаковка", 1500])
    return {
        "products": csv_bytes(
            ["product_id", "name", "category"],
            [
                ["P001", "Кофе", "Drinks"],
                ["P002", "Чай", "Drinks"],
                ["P003", "Сэндвич", "Food"],
            ],
        ),
        "sales": csv_bytes(
            ["date", "product_id", "product_name", "quantity", "unit_price", "unit_cost"], sales
        ),
        "expenses": csv_bytes(["date", "category", "description", "amount"], expenses),
    }


def load_demo(db: Session, user_id: UUID | None = None) -> DemoLoad:
    business_id = (
        uuid5(NAMESPACE_URL, f"profitleak/demo/{DEMO_VERSION}/{user_id}")
        if user_id
        else DEMO_BUSINESS_ID
    )
    with db.begin_nested():
        db.execute(
            insert(db, Business)
            .values(id=business_id, name="Кафе Тараз — демо", industry="cafe", is_demo=True)
            .on_conflict_do_nothing(index_elements=[Business.id])
        )
        if user_id is not None:
            db.execute(
                insert(db, BusinessMembership)
                .values(business_id=business_id, user_id=user_id, role="owner")
                .on_conflict_do_nothing(
                    index_elements=[BusinessMembership.business_id, BusinessMembership.user_id]
                )
            )
        existed = []
        for kind, data in build_demo_files().items():
            parsed = parse_file(f"{DEMO_VERSION}_{kind}.csv", data, kind)
            _, already_imported = confirm_import(db, business_id, kind, parsed)
            existed.append(already_imported)
        business = db.get(Business, business_id)
        # Reopening an existing personal demo also repairs metadata from older builds.
        business.is_demo = True
        db.flush()
        counts = {
            model: db.scalar(
                select(func.count()).select_from(model).where(model.business_id == business_id)
            )
            for model in (Sale, Expense, Product)
        }
        return DemoLoad(
            business=BusinessRead.model_validate(business),
            dataset_version=DEMO_VERSION,
            period=Period(date_from=DEMO_START, date_to=DEMO_END),
            sales_rows=counts[Sale],
            expense_rows=counts[Expense],
            product_count=counts[Product],
            already_loaded=all(existed),
        )
