import io
from datetime import datetime
from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from app.services import import_parser
from app.services.import_parser import FileProblem, parse_file

SALES_HEADER = "date,product_id,product_name,quantity,unit_price,unit_cost\n"
VALID_SALE = "2026-10-01,P001,Кофе,3,1200.10,450\n"


def xlsx_bytes(rows, second_sheet=False):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    if second_sheet:
        workbook.create_sheet("Other")
    target = io.BytesIO()
    workbook.save(target)
    workbook.close()
    return target.getvalue()


def test_csv_decimals_and_provenance():
    parsed = parse_file("../../sales.csv", (SALES_HEADER + "\n" + VALID_SALE).encode(), "sales")
    assert parsed.filename == "sales.csv"
    assert parsed.row_count == 1
    assert parsed.rows[0].source_row == 3
    assert parsed.rows[0].data.unit_price == Decimal("1200.10")
    assert parsed.rows[0].data.model_dump(mode="json")["unit_price"] == "1200.10"


@pytest.mark.parametrize(
    "value,field",
    [
        ("2026-02-30,P001,Coffee,1,10,5", "date"),
        ("2026-10-01T00:00:00,P001,Coffee,1,10,5", "date"),
        ("2026-W01-1,P001,Coffee,1,10,5", "date"),
        ("2026-10-01,P001,Coffee,-1,10,5", "quantity"),
        ("2026-10-01,P001,Coffee,0,10,5", "quantity"),
        ("2026-10-01,P001,Coffee,1,NaN,5", "unit_price"),
        ("2026-10-01,P001,Coffee,1,Infinity,5", "unit_price"),
        ("2026-10-01,P001,Coffee,1,10.001,5", "unit_price"),
        ("2026-10-01,P001,Coffee,1.0001,10,5", "quantity"),
        ("2026-10-01,P001,Coffee,1,10000000000000000,5", "unit_price"),
    ],
)
def test_invalid_row_values(value, field):
    parsed = parse_file("sales.csv", (SALES_HEADER + value).encode(), "sales")
    assert parsed.rows == []
    assert parsed.errors[0].row == 2
    assert parsed.errors[0].field == field


@pytest.mark.parametrize("header", ["date,date", "date,amount", "date,unknown"])
def test_bad_columns(header):
    parsed = parse_file("sales.csv", (header + "\n2026-10-01,5\n").encode(), "sales")
    assert parsed.errors
    assert all(error.row == 1 for error in parsed.errors)


def test_content_digest_normalizes_format_and_order():
    first = parse_file(
        "sales.csv",
        (SALES_HEADER + VALID_SALE + "2026-10-02,P001,Кофе,1,1000,400\n").encode(),
        "sales",
    )
    second = parse_file(
        "renamed.csv",
        (
            SALES_HEADER
            + "2026-10-02,P001, Кофе ,1.000,1000.00,400.00\n"
            + "2026-10-01,P001,Кофе,3.000,1200.10,450.00\n"
        ).encode(),
        "sales",
    )
    assert first.file_sha256 != second.file_sha256
    assert first.content_sha256 == second.content_sha256


def test_return_and_missing_cost():
    parsed = parse_file(
        "sales.csv",
        (
            SALES_HEADER.rstrip() + ",record_type\n" + "2026-10-01,P001,Coffee,1,1200,,return\n"
        ).encode(),
        "sales",
    )
    assert parsed.errors == []
    assert parsed.rows[0].data.unit_cost is None
    assert parsed.rows[0].data.record_type == "return"


def test_xlsx_blank_cost_and_equivalent_csv():
    data = xlsx_bytes(
        [SALES_HEADER.strip().split(","), [datetime(2026, 10, 1), "P001", "Coffee", 1, 1200, None]]
    )
    parsed = parse_file("sales.xlsx", data, "sales")
    csv = parse_file(
        "sales.csv", (SALES_HEADER + "2026-10-01,P001,Coffee,1,1200,\n").encode(), "sales"
    )
    assert parsed.errors == []
    assert parsed.rows[0].data.unit_cost is None
    assert parsed.content_sha256 == csv.content_sha256


def test_xlsx_formulas_are_rejected():
    data = xlsx_bytes(
        [
            SALES_HEADER.strip().split(","),
            [datetime(2026, 10, 1), "P001", "Coffee", 1, "=1000+200", 450],
        ]
    )
    parsed = parse_file("sales.xlsx", data, "sales")
    assert parsed.rows == []
    assert parsed.errors[0].field == "unit_price"


def test_numeric_dates_are_rejected():
    data = xlsx_bytes([SALES_HEADER.strip().split(","), [123456, "P001", "Coffee", 1, 1200, 450]])
    assert parse_file("sales.xlsx", data, "sales").errors[0].field == "date"


def test_multiple_sheets_are_rejected():
    with pytest.raises(FileProblem, match="один лист"):
        parse_file("sales.xlsx", xlsx_bytes([["date"]], second_sheet=True), "sales")


@pytest.mark.parametrize(
    "filename,data,code",
    [
        ("data.exe", b"hello", "unsupported_format"),
        ("sales.csv", b"\xff", "invalid_encoding"),
        ("sales.csv", b"\x00", "invalid_csv"),
        ("sales.xlsx", b"not a zip", "invalid_xlsx"),
        ("sales.csv", b'"unclosed', "invalid_csv"),
    ],
)
def test_malformed_files(filename, data, code):
    with pytest.raises(FileProblem) as error:
        parse_file(filename, data, "sales")
    assert error.value.code == code


def test_row_limit_and_error_limit(monkeypatch):
    monkeypatch.setattr(import_parser, "MAX_ROWS", 2)
    with pytest.raises(FileProblem) as error:
        parse_file("sales.csv", (SALES_HEADER + VALID_SALE * 3).encode(), "sales")
    assert error.value.code == "too_many_rows"
    monkeypatch.setattr(import_parser, "MAX_ROWS", 200)
    parsed = parse_file(
        "sales.csv", (SALES_HEADER + "2026-10-01,P001,Coffee,0,10,5\n" * 101).encode(), "sales"
    )
    assert parsed.error_count == 101
    assert len(parsed.errors) == 100


def test_expanded_zip_limit(monkeypatch):
    monkeypatch.setattr(import_parser, "MAX_EXPANDED_BYTES", 10)
    data = io.BytesIO()
    with ZipFile(data, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", "x" * 1000)
    with pytest.raises(FileProblem) as error:
        parse_file("sales.xlsx", data.getvalue(), "sales")
    assert error.value.code == "expanded_file_too_large"


def test_conflicting_product_names():
    parsed = parse_file(
        "sales.csv",
        (SALES_HEADER + VALID_SALE + "2026-10-01,P001,Tea,1,700,250\n").encode(),
        "sales",
    )
    assert parsed.errors[0].row == 3
    assert parsed.errors[0].field == "product_id"


def test_product_duplicate_ids_are_rejected():
    parsed = parse_file("products.csv", b"product_id,name\nP001,Coffee\nP001,Coffee\n", "products")
    assert parsed.errors[0].row == 3


@pytest.mark.parametrize("data", [b"", SALES_HEADER.encode()])
def test_empty_files_are_rejected(data):
    assert parse_file("sales.csv", data, "sales").errors
