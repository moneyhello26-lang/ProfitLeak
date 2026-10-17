"""Local, deterministic PDF export. No provider calls or database writes."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.core.i18n import translate
from app.models import Business
from app.schemas.analytics import Period
from app.services import analytics, insights
from app.services.advisor import LABELS, formatted, signal_title

FONT = "ProfitLeakSans"
pdfmetrics.registerFont(
    TTFont(FONT, str(Path(__file__).resolve().parents[1] / "assets/fonts/DejaVuSans.ttf"))
)
INK = colors.HexColor("#18342f")
TEAL = colors.HexColor("#087f70")
MUTED = colors.HexColor("#58716a")
PALE = colors.HexColor("#eef6f3")
STYLES = {
    "title": ParagraphStyle(
        "title", fontName=FONT, fontSize=21, leading=28, textColor=INK, spaceAfter=12
    ),
    "heading": ParagraphStyle(
        "heading",
        fontName=FONT,
        fontSize=13,
        leading=18,
        textColor=TEAL,
        spaceBefore=15,
        spaceAfter=8,
        keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body", fontName=FONT, fontSize=9, leading=14, textColor=INK, spaceAfter=7
    ),
    "small": ParagraphStyle(
        "small", fontName=FONT, fontSize=8, leading=12, textColor=MUTED, spaceAfter=7
    ),
}


def paragraph(text, style="body", system=True):
    text = translate(str(text)) if system else str(text)
    for dash in ("\u2011", "\u2013", "\u2014"):
        text = text.replace(dash, "-")
    return Paragraph(escape(text).replace("\n", "<br/>"), STYLES[style])


def dates(period):
    return f"{period.date_from:%d.%m.%Y} - {period.date_to:%d.%m.%Y}"


def table(rows, widths):
    result = Table(
        [
            [paragraph(cell, "small", system=index == 0) for cell in row]
            for index, row in enumerate(rows)
        ],
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dfe9e5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def decoration(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFont(FONT, 8)
    canvas.setFillColor(TEAL)
    canvas.drawString(42, height - 28, translate("ProfitLeak AI / Финансы под контролем"))
    canvas.setFillColor(MUTED)
    canvas.drawString(42, 27, translate("Сформировано локально / KZT / Шаблонные рекомендации"))
    canvas.drawRightString(width - 42, 27, translate("Страница {page}").format(page=doc.page))
    canvas.restoreState()


def export_pdf(db: Session, business: Business, period: Period) -> bytes:
    overview = analytics.summary(db, business.id, period)
    products = analytics.product_profitability(db, business.id, period, 10, 0)
    expenses = analytics.expense_categories(db, business.id, period)
    saved = insights.list_insights(db, business.id, period, None, None, 20, 0)
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=51,
        bottomMargin=47,
        title=translate("ProfitLeak AI - Финансовый отчёт"),
        author="ProfitLeak AI",
    )
    width = A4[0] - 84
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Almaty"))
    content = [
        paragraph("Финансовый отчёт", "title"),
        paragraph(business.name, system=False),
        paragraph(
            translate("Период: {period}\nСформирован: {time} (Алматы)").format(
                period=dates(period), time=now.strftime("%d.%m.%Y %H:%M")
            ),
            "small",
        ),
        paragraph("Основные показатели", "heading"),
    ]
    rows = [["Показатель", "Значение"]]
    for key, label in LABELS.items():
        metric = getattr(overview, key)
        rows.append(
            [
                translate(label),
                formatted(metric.value, "%" if key == "gross_margin_percent" else "KZT"),
            ]
        )
    content.append(table(rows, [width * 0.56, width * 0.44]))
    content.append(
        paragraph(
            translate(
                "Подтверждённые строки: продажи {sales}, расходы {expenses}. "
                "Продажи без себестоимости: {missing}."
            ).format(
                sales=overview.sales_rows,
                expenses=overview.expense_rows,
                missing=overview.missing_cost_rows,
            ),
            "small",
        )
    )
    if overview.missing_cost_rows:
        content.append(
            paragraph(
                "Прибыль и маржа недоступны при неполной себестоимости. "
                "Отсутствующие данные не заменяются нулём."
            )
        )
    content.append(paragraph("Расходы по категориям", "heading"))
    if expenses.categories:
        categories = sorted(expenses.categories, key=lambda row: row.amount, reverse=True)
        content.append(
            table(
                [
                    ["Категория", "Сумма", "Строки"],
                    *[
                        [
                            row.category,
                            formatted(row.amount),
                            row.expense_rows,
                        ]
                        for row in categories[:10]
                    ],
                ],
                [width * 0.42, width * 0.4, width * 0.18],
            )
        )
        content.append(
            paragraph(
                translate("Показано {shown} из {total} категорий.").format(
                    shown=min(10, len(categories)), total=len(categories)
                ),
                "small",
            )
        )
    else:
        content.append(paragraph("Расходы за выбранный период не загружены."))
    content.append(paragraph("Прибыльность товаров", "heading"))
    if products.items:
        content.append(
            table(
                [
                    ["Товар", "Выручка", "Валовая прибыль", "Маржа"],
                    *[
                        [
                            row.name,
                            formatted(row.revenue.value),
                            formatted(row.gross_profit.value),
                            formatted(row.gross_margin_percent.value, "%"),
                        ]
                        for row in products.items
                    ],
                ],
                [width * 0.26, width * 0.27, width * 0.29, width * 0.18],
            )
        )
        content.append(
            paragraph(
                translate(
                    "Показано {shown} из {total} товаров. Полный список доступен в приложении."
                ).format(shown=len(products.items), total=products.total),
                "small",
            )
        )
    else:
        content.append(paragraph("Продажи товаров за этот период отсутствуют."))
    content.append(
        paragraph(
            "Расчёты выполняет backend по подтверждённым импорту и датам. "
            "Возвраты вычитаются. Операционная прибыль не включает "
            "неизвестные налоги и иные незагруженные расходы.",
            "small",
        )
    )
    content.extend([PageBreak(), paragraph("Сигналы для проверки", "title")])
    if saved.analysis is None:
        content.append(
            paragraph(
                "Анализ за выбранный период ещё не запускался. "
                "Откройте детектор и запустите анализ, затем выгрузите отчёт снова."
            )
        )
    else:
        content.append(
            paragraph(
                translate(
                    "Правила: {version}. Сигналов: {total}. Показано: {shown}. Анализ: {time}."
                ).format(
                    version=saved.analysis.rules_version,
                    total=saved.total,
                    shown=len(saved.items),
                    time=saved.analysis.analyzed_at.astimezone(ZoneInfo("Asia/Almaty")).strftime(
                        "%d.%m.%Y %H:%M"
                    ),
                ),
                "small",
            )
        )
        if saved.analysis.stale:
            content.append(
                paragraph(
                    "ВНИМАНИЕ: анализ устарел после нового импорта. "
                    "KPI выше рассчитаны по текущим данным, а сигналы ниже "
                    "сохранены ранее. Перед решениями повторите анализ."
                )
            )
        if not saved.items:
            content.append(
                paragraph(
                    "Сигналов по текущим правилам не найдено. Это не доказывает "
                    "отсутствие проблем. Проверьте достаточность данных."
                )
            )
        for check in saved.analysis.checks:
            if check.status == "insufficient_data" or check.skipped_entities:
                content.append(
                    paragraph(
                        f"{check.type}: {check.reason} "
                        + translate("Пропущено объектов: {count}.").format(
                            count=check.skipped_entities
                        ),
                        "small",
                    )
                )
    content.append(
        paragraph(
            "Сигналы не являются доказанными потерями. Сценарные оценки могут "
            "пересекаться, не суммируются и не гарантируют экономию."
        )
    )
    priority = {
        key: translate(value)
        for key, value in {"high": "Высокий", "medium": "Средний", "low": "Низкий"}.items()
    }
    for index, item in enumerate(saved.items):
        if index:
            content.append(PageBreak())
        ev = item.evidence
        content.extend(
            [
                Spacer(1, 8),
                paragraph(signal_title(item), "heading"),
                paragraph(
                    translate(
                        "Приоритет: {priority}. Достоверность: {confidence}. "
                        "Текущий период: {period}."
                    ).format(
                        priority=priority[item.severity],
                        confidence=priority[item.confidence],
                        period=dates(ev.current_period),
                    ),
                    "small",
                ),
                paragraph(ev.explanation),
            ]
        )
        metrics = [
            ["Факт", "Значение"],
            [
                translate("Текущее значение"),
                formatted(ev.current_value, "%" if ev.value_unit == "percent" else "KZT"),
            ],
        ]
        if ev.baseline_value is not None:
            metrics.append(
                [
                    translate("Базовое значение"),
                    formatted(ev.baseline_value, "%" if ev.value_unit == "percent" else "KZT"),
                ]
            )
        if ev.deviation_percent is not None:
            metrics.append([translate("Изменение"), formatted(ev.deviation_percent, "%")])
        if ev.deviation_pp is not None:
            metrics.append([translate("Изменение маржи"), formatted(ev.deviation_pp, "п.п.")])
        metrics.append(
            [
                translate("Сценарная оценка"),
                formatted(item.potential_savings_kzt)
                if item.potential_savings_kzt is not None
                else translate("Не оценена"),
            ]
        )
        content.append(table(metrics, [width * 0.52, width * 0.48]))
        if ev.baseline_period:
            content.append(
                paragraph(
                    translate("Базовый период: {period}.").format(period=dates(ev.baseline_period)),
                    "small",
                )
            )
        content.extend(
            [
                paragraph(translate("Правило: ") + ev.formula),
                paragraph(ev.caveat, "small"),
                paragraph("Что проверить", "heading"),
                paragraph(item.recommendation),
            ]
        )
        if ev.savings_assumption:
            content.append(
                paragraph(translate("Условие оценки: ") + ev.savings_assumption, "small")
            )
        source_rows = ev.source_rows[:6]
        if ev.baseline_period:
            source_rows = [
                row
                for row in ev.source_rows
                if ev.current_period.date_from <= row.date <= ev.current_period.date_to
            ][:3]
            source_rows += [
                row
                for row in ev.source_rows
                if ev.baseline_period.date_from <= row.date <= ev.baseline_period.date_to
            ][:3]
        source_table = table(
            [
                ["Файл", "Строка", "Дата", "Сумма"],
                *[
                    [
                        row.filename,
                        row.source_row,
                        f"{row.date:%d.%m.%Y}",
                        formatted(row.amount),
                    ]
                    for row in source_rows
                ],
            ],
            [width * 0.43, width * 0.12, width * 0.21, width * 0.24],
        )
        source_note = paragraph(
            translate(
                "Показано {shown} из {total} исходных строк; полный образец "
                "доступен в детекторе. Возвраты показаны положительными "
                "суммами и вычитаются при расчётах."
            ).format(shown=len(source_rows), total=ev.source_rows_total),
            "small",
        )
        content.append(KeepTogether([paragraph("Источники", "heading"), source_table, source_note]))
    document.build(content, onFirstPage=decoration, onLaterPages=decoration)
    return output.getvalue()
