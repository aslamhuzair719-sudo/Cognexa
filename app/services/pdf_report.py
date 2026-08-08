"""Generate a staff-facing verification report PDF."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SECTION_KEYS = [
    ("customer_information_validation", "Customer information validation"),
    ("cnic_validation", "CNIC validation"),
    ("payslip_validation", "Payslip validation"),
    ("bank_statement_validation", "Bank statement validation"),
    ("cross_validation", "Cross validation"),
]


def _safe(value: Any) -> str:
    if value is None:
        return "—"
    return str(value)


def build_verification_pdf(
    report: Dict[str, Any],
    *,
    applicant_name: Optional[str] = None,
    application_id: Optional[str] = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Verification Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#0b4f46"),
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "H2Custom",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#10241f"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
    )
    small = ParagraphStyle(
        "SmallCustom",
        parent=styles["BodyText"],
        fontSize=8,
        textColor=colors.HexColor("#4a635c"),
        leading=10,
    )

    story: List[Any] = []
    story.append(Paragraph("Cognexa — Verification System", title_style))
    if applicant_name or application_id:
        story.append(
            Paragraph(
                f"Applicant: {_safe(applicant_name)} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"Application ID: {_safe(application_id)}",
                small,
            )
        )
    story.append(Spacer(1, 4 * mm))

    story.append(
        Paragraph(
            f"<b>Status:</b> {_safe(report.get('application_status'))} &nbsp;&nbsp; "
            f"<b>Score:</b> {_safe(report.get('overall_score'))}% &nbsp;&nbsp; "
            f"<b>Recommendation:</b> {_safe(report.get('recommendation'))}",
            body,
        )
    )
    detail = report.get("recommendation_detail") or ""
    if detail:
        story.append(Paragraph(_safe(detail), small))

    summary = report.get("summary") or []
    if summary:
        story.append(Paragraph("Summary", h2))
        for item in summary:
            story.append(Paragraph(f"• {_safe(item)}", body))

    app_summary = report.get("application_summary") or {}
    if app_summary:
        story.append(Paragraph("Application summary", h2))
        rows = [["Field", "Value"]]
        for key, value in app_summary.items():
            rows.append([key.replace("_", " ").title(), _safe(value)])
        story.append(_table(rows))

    docs = report.get("uploaded_documents") or []
    if docs:
        story.append(Paragraph("Uploaded documents", h2))
        rows = [["Document", "Uploaded", "Classified", "Extracted"]]
        for d in docs:
            rows.append(
                [
                    _safe(d.get("document_label")),
                    "Yes" if d.get("uploaded") else "No",
                    _safe(d.get("classified_as")),
                    "OK" if d.get("extraction_ok") else "FAIL",
                ]
            )
        story.append(_table(rows))

    quality = report.get("image_quality") or []
    if quality:
        story.append(Paragraph("Image quality", h2))
        rows = [["Document", "Overall", "Readable"]]
        for q in quality:
            rows.append(
                [
                    _safe(q.get("document_label")),
                    _safe(q.get("overall")),
                    "Yes" if q.get("readable") else "No",
                ]
            )
        story.append(_table(rows))

    for key, title in SECTION_KEYS:
        section = report.get(key) or {}
        comparisons = section.get("comparisons") or []
        story.append(
            Paragraph(
                f"{title} — {_safe(section.get('status'))}",
                h2,
            )
        )
        if not comparisons:
            story.append(Paragraph("No comparisons.", small))
            continue
        rows = [["Field", "Customer", "Document", "Result"]]
        for c in comparisons:
            rows.append(
                [
                    _safe(c.get("field")),
                    _safe(c.get("customer_value")),
                    _safe(c.get("document_value")),
                    _safe(c.get("result")),
                ]
            )
        story.append(_table(rows))

    missing = report.get("missing_information") or []
    warnings = report.get("warnings") or []
    story.append(Paragraph("Missing information", h2))
    if missing:
        for item in missing:
            story.append(Paragraph(f"• {_safe(item)}", body))
    else:
        story.append(Paragraph("None", small))

    story.append(Paragraph("Warnings", h2))
    if warnings:
        for item in warnings:
            story.append(Paragraph(f"• {_safe(item)}", body))
    else:
        story.append(Paragraph("None", small))

    doc.build(story)
    return buffer.getvalue()


def _table(rows: List[List[str]]) -> Table:
    table = Table(rows, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f3f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b4f46")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c7d8d1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table
