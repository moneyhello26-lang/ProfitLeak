"""Generate reproducible synthetic businesses, validate imports and optionally load locally.

Run from the repository root:
backend/.venv/Scripts/python.exe backend/scripts/generate_realistic_data.py --load
"""

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.import_parser import parse_file  # noqa: E402

START, END = date(2026, 1, 1), date(2026, 10, 14)
SHOCK = date(2026, 9, 15)
VERSION = "realistic-businesses-v1"
D = Decimal

# name, category, selling price, unit cost, average daily demand, seasonal group
CAFE = [
    ("Эспрессо", "Кофе", 850, 220, 12, "hot"),
    ("Американо", "Кофе", 1000, 260, 26, "hot"),
    ("Капучино 250 мл", "Кофе", 1350, 450, 32, "hot"),
    ("Латте 350 мл", "Кофе", 1550, 540, 27, "hot"),
    ("Флэт уайт", "Кофе", 1500, 490, 11, "hot"),
    ("Раф ванильный", "Кофе", 1800, 710, 13, "hot"),
    ("Айс-латте", "Холодные напитки", 1650, 560, 15, "cold"),
    ("Лимонад цитрусовый", "Холодные напитки", 1400, 380, 14, "cold"),
    ("Матча-латте", "Напитки", 1750, 650, 9, "hot"),
    ("Чай чёрный", "Чай", 850, 180, 16, "hot"),
    ("Чай облепиховый", "Чай", 1250, 390, 12, "hot"),
    ("Какао", "Напитки", 1300, 430, 10, "hot"),
    ("Круассан классический", "Выпечка", 950, 380, 22, "food"),
    ("Круассан миндальный", "Выпечка", 1450, 650, 14, "food"),
    ("Синнабон", "Выпечка", 1200, 490, 13, "food"),
    ("Маффин шоколадный", "Выпечка", 1000, 390, 12, "food"),
    ("Чизкейк", "Десерты", 1850, 790, 11, "food"),
    ("Медовик", "Десерты", 1650, 710, 10, "food"),
    ("Сэндвич с курицей", "Еда", 2100, 1050, 17, "food"),
    ("Панини с сыром", "Еда", 1900, 880, 12, "food"),
    ("Овсяная каша", "Завтраки", 1500, 520, 10, "food"),
    ("Сырники", "Завтраки", 2200, 920, 14, "food"),
    ("Гранола с йогуртом", "Завтраки", 1800, 780, 9, "food"),
    ("Вода 0,5 л", "Напитки", 500, 210, 18, "cold"),
]
GROCERY = [
    ("Молоко 3,2% 1 л", "Молочные продукты", 650, 500, 44, "basic"),
    ("Кефир 1 л", "Молочные продукты", 600, 450, 22, "basic"),
    ("Сметана 400 г", "Молочные продукты", 950, 720, 12, "basic"),
    ("Йогурт 250 г", "Молочные продукты", 450, 310, 23, "basic"),
    ("Масло сливочное 180 г", "Молочные продукты", 1350, 1050, 11, "basic"),
    ("Сыр 200 г", "Молочные продукты", 1450, 1070, 13, "basic"),
    ("Яйца 10 шт", "Бакалея", 850, 650, 31, "basic"),
    ("Хлеб пшеничный", "Хлеб", 230, 160, 68, "basic"),
    ("Хлеб ржаной", "Хлеб", 340, 240, 28, "basic"),
    ("Рис 1 кг", "Бакалея", 750, 550, 19, "basic"),
    ("Гречка 800 г", "Бакалея", 650, 460, 14, "basic"),
    ("Макароны 500 г", "Бакалея", 480, 320, 24, "basic"),
    ("Мука 2 кг", "Бакалея", 850, 640, 12, "basic"),
    ("Сахар 1 кг", "Бакалея", 520, 400, 19, "basic"),
    ("Масло подсолнечное 1 л", "Бакалея", 1100, 830, 17, "basic"),
    ("Чай 100 пакетиков", "Бакалея", 2100, 1480, 8, "basic"),
    ("Кофе растворимый 95 г", "Бакалея", 2600, 1870, 6, "basic"),
    ("Вода 1,5 л", "Напитки", 350, 190, 38, "cold"),
    ("Сок 1 л", "Напитки", 950, 630, 18, "cold"),
    ("Лимонад 1 л", "Напитки", 620, 400, 23, "cold"),
    ("Мороженое пломбир", "Заморозка", 420, 260, 26, "cold"),
    ("Пельмени 800 г", "Заморозка", 2300, 1670, 10, "basic"),
    ("Куриное филе 1 кг", "Мясо", 2300, 1820, 14, "basic"),
    ("Яблоки 1 кг", "Овощи и фрукты", 850, 550, 19, "produce"),
    ("Бананы 1 кг", "Овощи и фрукты", 1250, 900, 16, "produce"),
    ("Картофель 1 кг", "Овощи и фрукты", 320, 210, 36, "produce"),
    ("Помидоры 1 кг", "Овощи и фрукты", 950, 650, 21, "produce"),
    ("Огурцы 1 кг", "Овощи и фрукты", 800, 510, 20, "produce"),
    ("Шоколад 90 г", "Сладости", 750, 490, 24, "basic"),
    ("Печенье 300 г", "Сладости", 650, 420, 18, "basic"),
]
FLOWERS = [
    ("Букет 7 роз", "Букеты", 13500, 6100, 4, "rose"),
    ("Букет 15 роз", "Букеты", 26500, 13000, 2.5, "rose"),
    ("Букет 25 роз", "Букеты", 42500, 22000, 1.1, "rose"),
    ("Букет кустовых роз", "Букеты", 18500, 7900, 2, "rose"),
    ("Букет из хризантем", "Букеты", 11500, 4400, 2.3, "flower"),
    ("Букет альстромерий", "Букеты", 14500, 5500, 1.9, "flower"),
    ("Букет 15 тюльпанов", "Сезонные букеты", 16500, 6800, 3.1, "tulip"),
    ("Букет из пионов", "Сезонные букеты", 24500, 10400, 1.8, "peony"),
    ("Авторский букет S", "Авторские букеты", 15500, 5900, 2.5, "flower"),
    ("Авторский букет M", "Авторские букеты", 24500, 10400, 1.7, "flower"),
    ("Авторский букет L", "Авторские букеты", 36500, 16200, 0.9, "flower"),
    ("Цветочная коробка S", "Композиции", 19500, 8200, 1.6, "flower"),
    ("Цветочная коробка M", "Композиции", 29500, 13700, 1, "flower"),
    ("Свадебный букет", "Свадьбы", 38500, 15100, 0.45, "wedding"),
    ("Бутоньерка", "Свадьбы", 4500, 1100, 0.6, "wedding"),
    ("Комнатная орхидея", "Растения", 14500, 8200, 0.65, "plant"),
    ("Суккулент в горшке", "Растения", 4500, 1900, 1.4, "plant"),
    ("Открытка", "Дополнения", 700, 150, 6, "extra"),
    ("Воздушный шар", "Дополнения", 2200, 700, 2.7, "extra"),
    ("Ваза стеклянная", "Дополнения", 5500, 2500, 0.8, "extra"),
]
PROFILES = [
    dict(
        slug="01_coffee",
        name="Кофейня «Квартал» · синтетика",
        industry="cafe",
        products=CAFE,
        seed=8101,
        rent=480000,
        wages=1850000,
        utilities=135000,
        software=28000,
        marketing=12000,
        packaging=42,
        delivery=0.028,
    ),
    dict(
        slug="02_grocery",
        name="Магазин «У дома» · синтетика",
        industry="retail",
        products=GROCERY,
        seed=8102,
        rent=320000,
        wages=1050000,
        utilities=115000,
        software=22000,
        marketing=5500,
        packaging=8,
        delivery=0.004,
    ),
    dict(
        slug="03_flowers",
        name="Цветочная «Лепесток» · синтетика",
        industry="retail",
        products=FLOWERS,
        seed=8103,
        rent=360000,
        wages=1250000,
        utilities=85000,
        software=18000,
        marketing=14500,
        packaging=90,
        delivery=0.045,
    ),
]


def money(v):
    return D(str(v)).quantize(D(".01"), rounding=ROUND_HALF_UP)


def csv_file(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def season(profile, group, day):
    summer = 0.5 + 0.5 * math.sin((day.timetuple().tm_yday - 105) / 365 * 2 * math.pi)
    if profile["slug"] == "03_flowers":
        if group == "tulip":
            return 1.9 if day.month in (2, 3) else (0.6 if day.month == 4 else 0)
        if group == "peony":
            return 2.3 if day.month in (5, 6) else (0.5 if day.month == 7 else 0)
        if group == "wedding":
            return 2 if day.month in (5, 6, 7, 8, 9) and day.weekday() in (4, 5, 6) else 0.5
        return 1 - 0.35 * summer
    if group == "cold":
        return 0.35 + 1.6 * summer
    if group == "hot":
        return 1.28 - 0.45 * summer
    if group == "produce":
        return 1 + 0.3 * summer
    return 1


def generate(profile):
    rng = random.Random(profile["seed"])
    sales, expenses, events = [], [], []
    prefix = profile["slug"].split("_")[1].upper()[:3]
    products = [
        dict(product_id=f"{prefix}{i:03d}", name=item[0], category=item[1])
        for i, item in enumerate(profile["products"], 1)
    ]
    daily = defaultdict(lambda: dict(revenue=D(0), cogs=D(0), units=D(0)))
    period_days = (END - START).days + 1
    closed = {date(2026, 1, 1)}
    if prefix == "COF":
        closed |= {date(2026, 1, 2), date(2026, 8, 18), date(2026, 8, 19)}
    events.append(
        "Выходные и случайные колебания трафика влияют на продажи; "
        "закрытые дни не заполнены нулями."
    )
    for offset in range(period_days):
        day = START + timedelta(days=offset)
        if day in closed:
            continue
        weekend = day.weekday() >= 5
        traffic = rng.lognormvariate(-0.025, 0.19)
        traffic *= (1.22 if weekend else 0.94) if prefix != "GRO" else (1.12 if weekend else 0.97)
        traffic *= 1 + 0.1 * offset / period_days
        if day.day in (5, 6, 7, 25, 26, 27):
            traffic *= 1.1
        if prefix == "FLO":
            for holiday, peak in [
                (date(2026, 2, 14), 4.0),
                (date(2026, 3, 8), 7.0),
                (date(2026, 9, 1), 3.7),
            ]:
                distance = abs((day - holiday).days)
                if distance <= 2:
                    traffic *= 1 + (peak - 1) * math.exp(-distance * distance / 1.7)
        if date(2026, 6, 10) <= day <= date(2026, 6, 20) and prefix == "COF":
            traffic *= 0.72
        for idx, (name, category, price, cost, demand, group) in enumerate(profile["products"]):
            seasonal = season(profile, group, day)
            if not seasonal or rng.random() < 0.018:
                continue
            # A supplier disruption affects one product, while other sales continue.
            if prefix == "GRO" and idx == 4 and date(2026, 8, 4) <= day <= date(2026, 8, 9):
                continue
            volume = demand * traffic * seasonal * rng.lognormvariate(-0.04, 0.24)
            if day >= SHOCK and prefix == "COF" and idx == 18:
                volume *= 0.52
            qty = int(volume + rng.random())
            if qty <= 0:
                continue
            unit_price = money(round(price * (1.05 if day.month >= 7 else 1) / 10) * 10)
            unit_cost = money(
                cost * (1 + 0.009 * (day.month - 1)) * (1 + rng.uniform(-0.025, 0.025))
            )
            if prefix == "GRO" and group == "produce":
                unit_cost = money(
                    unit_cost * D(str(1.22 - 0.42 * math.sin((day.month - 2) / 12 * 2 * math.pi)))
                )
            if day >= SHOCK:
                if prefix == "COF" and idx in (2, 3):
                    unit_cost = money(unit_cost * D("1.55"))
                if prefix == "GRO" and idx in (0, 6):
                    unit_cost = money(unit_cost * D("1.15"))
                if prefix == "FLO" and group == "rose":
                    unit_cost = money(unit_cost * D("1.38"))
            if prefix == "FLO" and day.month == 3 and day.day in (6, 7, 8):
                unit_price = money(unit_price * D("1.12"))
                unit_cost = money(unit_cost * D("1.25"))
            # Weighted goods are sold in kilograms with three decimal places.
            quantity = D(qty)
            if prefix == "GRO" and (group == "produce" or idx == 22):
                quantity = (D(str(volume)) * D(str(rng.uniform(0.7, 1.2)))).quantize(D(".001"))
            discount_qty = D(0)
            if rng.random() < 0.22 and quantity >= 4:
                discount_qty = (quantity * D(str(rng.uniform(0.12, 0.32)))).quantize(D(".001"))
                if quantity == quantity.to_integral():
                    discount_qty = discount_qty.to_integral(rounding=ROUND_HALF_UP)
            variants = [(quantity - discount_qty, unit_price)]
            if discount_qty:
                variants.append((discount_qty, money(unit_price * D(".90"))))
            for amount, actual_price in variants:
                row = dict(
                    date=day.isoformat(),
                    product_id=products[idx]["product_id"],
                    product_name=name,
                    quantity=str(amount),
                    unit_price=str(actual_price),
                    unit_cost=str(unit_cost),
                    record_type="sale",
                )
                sales.append(row)
                daily[day]["revenue"] += money(amount * actual_price)
                daily[day]["cogs"] += money(amount * unit_cost)
                daily[day]["units"] += amount
            if rng.random() < (0.018 if prefix == "GRO" else 0.009) and quantity >= 2:
                returned = D(".500") if prefix == "GRO" and group == "produce" else D(1)
                sales.append(
                    dict(
                        date=day.isoformat(),
                        product_id=products[idx]["product_id"],
                        product_name=name,
                        quantity=str(returned),
                        unit_price=str(unit_price),
                        unit_cost=str(unit_cost),
                        record_type="return",
                    )
                )
                daily[day]["revenue"] -= money(returned * unit_price)
                daily[day]["cogs"] -= money(returned * unit_cost)
                daily[day]["units"] -= returned

    def expense(day, category, description, amount, record_type="expense"):
        expenses.append(
            dict(
                date=day.isoformat(),
                category=category,
                description=description,
                amount=str(money(amount)),
                record_type=record_type,
            )
        )

    for offset in range(period_days):
        day = START + timedelta(days=offset)
        if day.day == 1:
            expense(day, "Rent", f"Аренда помещения за {day:%Y-%m}", profile["rent"])
        if day.day in (10, 25):
            expense(
                day,
                "Salary",
                f"Фонд оплаты труда, включая взносы; {day:%Y-%m-%d}",
                profile["wages"] / 2,
            )
        if day.day == 15:
            expense(
                day,
                "Utilities",
                f"Коммунальные услуги за предыдущий месяц; счёт {day:%Y%m}",
                profile["utilities"]
                * (1.2 if day.month in (1, 2, 7, 8) else 0.95)
                * rng.uniform(0.9, 1.1),
            )
        if day.day == 5:
            expense(day, "Software", f"Касса, учёт и интернет за {day:%Y-%m}", profile["software"])
        if day not in daily:
            continue
        stats = daily[day]
        expense(day, "BankFees", f"Эквайринг, реестр {day:%Y%m%d}", stats["revenue"] * D(".0095"))
        expense(
            day,
            "Delivery",
            f"Комиссии и доставка заказов {day:%Y-%m-%d}",
            stats["revenue"] * D(str(profile["delivery"])),
        )
        pack = profile["packaging"] * (1.6 if day >= SHOCK and prefix == "COF" else 1)
        expense(
            day,
            "Packaging",
            f"Упаковка и расходные материалы, накладная {day:%Y%m%d}",
            float(stats["units"]) * pack * rng.uniform(0.9, 1.1),
        )
        if day.weekday() in (0, 2, 4):
            spend = profile["marketing"] * rng.uniform(0.8, 1.25)
            if prefix == "FLO" and day >= SHOCK:
                spend *= 1.65
            expense(day, "Marketing", f"Реклама и продвижение; кампания {day:%Y-%m-%d}", spend)
        if day.weekday() == 1:
            expense(
                day,
                "Cleaning",
                f"Уборка и бытовые средства, акт {day:%Y%m%d}",
                rng.randint(4500, 10500),
            )
        if day.weekday() in (1, 4):
            expense(
                day,
                "Spoilage",
                f"Списания непроданных остатков по себестоимости, акт {day:%Y%m%d}",
                stats["cogs"]
                * D(str(0.11 if prefix == "FLO" else 0.035))
                * D(str(rng.uniform(0.7, 1.4))),
            )
        if day.day == 20:
            expense(
                day,
                "Repairs",
                f"Обслуживание оборудования, акт {day:%Y%m}",
                rng.randint(12000, 42000),
            )
        if day.day == 22 and day.month in (3, 6, 9):
            expense(
                day,
                "Packaging",
                f"Возврат поставщика за бракованную упаковку {day:%Y%m}",
                rng.randint(3000, 7000),
                "refund",
            )
    expense(
        date(2026, 8, 18),
        "Repairs",
        "Внеплановый ремонт оборудования, акт REP-0818",
        285000 if prefix == "COF" else 95000,
    )
    # One deliberately repeated document to exercise human review of duplicate candidates.
    duplicate = dict(
        date="2026-10-06",
        category="Repairs",
        description=f"Техобслуживание, акт {prefix}-1006",
        amount="18500.00",
        record_type="expense",
    )
    expenses.extend([duplicate.copy(), duplicate.copy()])
    events += [
        "Одна пара одинаковых строк техобслуживания от 06.10.2026 добавлена намеренно.",
        "Скидки отражены фактической ценой. "
        "Возвраты продаж и расходов имеют отдельный record_type.",
    ]
    if prefix == "COF":
        events += [
            "С 15.09 выросла себестоимость капучино и латте, упаковка подорожала на 60%.",
            "С 15.09 упал спрос на сэндвич с курицей. 18–19.08 кафе закрыто на ремонт.",
            "10–20.06 сниженный трафик. Холодные напитки популярнее летом.",
        ]
    elif prefix == "GRO":
        events += [
            "С 15.09 выросла закупочная цена молока и яиц при прежней цене продажи.",
            "Овощи, фрукты и куриное филе продаются на вес. "
            "04–09.08 отсутствовало сливочное масло.",
        ]
    else:
        events += [
            "Смоделированы пики спроса 14 февраля, 8 марта и 1 сентября.",
            "Тюльпаны и пионы доступны в сезон. Свадебные заказы чаще летом по выходным.",
            "С 15.09 подорожали розы и выросли расходы на рекламу.",
        ]
    sales.sort(key=lambda r: (r["date"], r["product_id"], r["record_type"], r["unit_price"]))
    expenses.sort(key=lambda r: (r["date"], r["category"], r["description"]))
    return products, sales, expenses, events


def totals(sales, expenses):
    revenue = sum(
        (
            (-1 if r["record_type"] == "return" else 1)
            * money(D(r["quantity"]) * D(r["unit_price"]))
            for r in sales
        ),
        D(0),
    )
    cogs = sum(
        (
            (-1 if r["record_type"] == "return" else 1)
            * money(D(r["quantity"]) * D(r["unit_cost"]))
            for r in sales
        ),
        D(0),
    )
    opex = sum(
        ((-1 if r["record_type"] == "refund" else 1) * D(r["amount"]) for r in expenses), D(0)
    )
    return {
        k: str(money(v))
        for k, v in dict(
            revenue=revenue,
            cogs=cogs,
            gross_profit=revenue - cogs,
            operating_expenses=opex,
            operating_profit=revenue - cogs - opex,
        ).items()
    }


def load_local(folder, manifest):
    import httpx

    base = "http://127.0.0.1:8000/api/v1"
    with httpx.Client(timeout=180) as client:

        def get(path, **kwargs):
            response = client.get(base + path, **kwargs)
            response.raise_for_status()
            return response.json()

        def post(path, **kwargs):
            response = client.post(base + path, **kwargs)
            response.raise_for_status()
            return response.json()

        existing = get("/businesses", params={"limit": 100})
        for business in manifest["businesses"]:
            found = next((x for x in existing if x["name"] == business["name"]), None)
            if found is None:
                found = post(
                    "/businesses", json={"name": business["name"], "industry": business["industry"]}
                )
                existing.append(found)
            identity = found["id"]
            for kind in ("products", "sales", "expenses"):
                source = folder / business["slug"] / (kind + ".csv")
                payload = {"business_id": identity, "kind": kind}
                files = {"file": (source.name, source.read_bytes(), "text/csv")}
                preview = post("/imports/preview", data=payload, files=files)
                if preview["existing_import_id"]:
                    continue
                assert preview["can_confirm"], preview["errors"]
                post(
                    "/imports/confirm",
                    data=dict(payload, preview_token=preview["preview_token"]),
                    files=files,
                )
            params = {
                "business_id": identity,
                "date_from": START.isoformat(),
                "date_to": END.isoformat(),
            }
            summary = get("/dashboard/summary", params=params)
            for metric, expected in business["totals"].items():
                assert D(summary[metric]["value"]) == D(expected), (
                    business["name"],
                    metric,
                    summary[metric],
                    expected,
                )
            assert summary["sales_rows"] == business["counts"]["sales"]
            assert summary["expense_rows"] == business["counts"]["expenses"]
            analysis = post("/analysis/run", json=params)
            signals = get("/insights", params=dict(params, limit=100))
            business["loaded_business_id"] = identity
            business["analysis"] = analysis
            business["signals"] = signals
            business["default_analysis"] = post("/analysis/run", json={"business_id": identity})
            business["default_signals"] = get(
                "/insights", params={"business_id": identity, "limit": 100}
            )
            business["api_verified"] = True
            print("Loaded and reconciled:", business["name"], business["counts"], flush=True)
    (folder / "loaded_businesses.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "output/ProfitLeak_Realistic_Business_Data"
    )
    parser.add_argument("--load", action="store_true")
    options = parser.parse_args()
    options.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(
        version=VERSION,
        synthetic=True,
        currency="KZT",
        date_from=str(START),
        date_to=str(END),
        businesses=[],
    )
    for profile in PROFILES:
        folder = options.output_dir / profile["slug"]
        folder.mkdir(exist_ok=True)
        products, sales, expenses, events = generate(profile)
        data = {"products": products, "sales": sales, "expenses": expenses}
        hashes = {}
        for kind, rows in data.items():
            path = folder / (kind + ".csv")
            csv_file(path, rows)
            parsed = parse_file(path.name, path.read_bytes(), kind)
            assert not parsed.error_count, (profile["name"], kind, parsed.errors[:3])
            assert len(parsed.rows) == len(rows)
            hashes[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert len({tuple(r.values()) for r in products}) == len(products)
        assert all(START.isoformat() <= r["date"] <= END.isoformat() for r in sales + expenses)
        assert len({r["unit_price"] for r in sales}) > len(products)
        monthly = []
        for month in range(1, 11):
            key = f"2026-{month:02d}"
            m_sales = [r for r in sales if r["date"].startswith(key)]
            m_expenses = [r for r in expenses if r["date"].startswith(key)]
            monthly.append(dict(month=key, **totals(m_sales, m_expenses)))
        csv_file(folder / "monthly_summary_reference.csv", monthly)
        business = dict(
            slug=profile["slug"],
            name=profile["name"],
            industry=profile["industry"],
            seed=profile["seed"],
            counts={k: len(v) for k, v in data.items()},
            totals=totals(sales, expenses),
            return_rows=sum(r["record_type"] == "return" for r in sales),
            refund_rows=sum(r["record_type"] == "refund" for r in expenses),
            sales_days=len({r["date"] for r in sales}),
            events=events,
            sha256=hashes,
        )
        manifest["businesses"].append(business)
        details = "\n".join("- " + event for event in events)
        (folder / "README.md").write_text(
            f"# {profile['name']}\n\nСинтетические операции, не данные реального предприятия.\n"
            f"Период: {START}–{END}. Валюта KZT.\n\n{details}\n\n"
            "products, sales, expenses импортируются отдельно в таком порядке.\n"
            "monthly_summary_reference.csv — контрольные итоги, не файл импорта.\n",
            encoding="utf-8",
        )
        # JSON is an intermediate source for the separate XLSX exporter.
        (folder / "source.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(profile["name"], business["counts"], business["totals"], flush=True)
    (options.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (options.output_dir / "README.md").write_text(
        "# Реалистичные синтетические данные ProfitLeak\n\n"
        f"Три разных предприятия, {START}–{END}, KZT. "
        "Все данные придуманы моделью и генератором, "
        "не получены от реального бизнеса и не являются рыночной статистикой. "
        "Цены, спрос и расходы — "
        "сценарные предположения, а не подтверждённые средние по Казахстану.\n\n"
        "Внутри каждой папки: products.csv, sales.csv, expenses.csv. Сначала импортируйте товары, "
        "затем продажи и расходы в отдельный бизнес. CSV имеет UTF-8 BOM и разделитель-запятую. "
        "Если доступны XLSX, они содержат те же записи: выбирайте один формат для каждого типа.\n\n"
        "Продажи агрегированы по дню, товару и фактической цене, это не отдельные чеки. "
        "Есть скидки, возвраты, весовые товары, периоды отсутствия товара, сезонный ассортимент и "
        "разные цены/себестоимость. Расходы включают аренду, оплату труда, упаковку, комиссии, "
        "доставку, рекламу, списания и ремонт. "
        "Себестоимость проданных товаров уже находится в продажах: "
        "закупки запасов повторно в расходы не включены. "
        "Списания касаются только непроданных остатков.\n\n"
        "Расходы и продажи датированы датой операции, "
        "без начисления и полного бухгалтерского учёта. "
        "Октябрь неполный, по 14.10.2026: его нельзя напрямую сравнивать с полным месяцем. "
        "Деньги положительные: return уменьшает продажи и себестоимость, refund уменьшает расходы. "
        "Себестоимость заполнена полностью, чтобы графики прибыли оставались доступны. "
        "Операционная прибыль не равна чистой прибыли после налогов.\n\n"
        "По одному возможному дубликату техобслуживания на бизнес добавлено специально. "
        "Повторять такой импорт вручную не нужно. Детектор сравнивает последние 30 дней "
        "(15.09–14.10) с предыдущими 30 днями (16.08–14.09). "
        "Не каждый скачок означает нарушение: "
        "сезонность и смена спроса также влияют на показатели.\n\n"
        "manifest.json содержит контрольные суммы, количество строк и финансовые итоги. "
        "monthly_summary_reference.csv в каждой папке содержит "
        "независимые контрольные итоги по месяцам. "
        "Эти файлы не загружаются через интерфейс импорта. "
        "Генератор воспроизводим по фиксированным seed.\n",
        encoding="utf-8",
    )
    if options.load:
        load_local(options.output_dir, manifest)


if __name__ == "__main__":
    main()
