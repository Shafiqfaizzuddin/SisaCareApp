"""Formatted aggregate-only PDF; no reporter identity or exact coordinates."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape


def render_pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.graphics.shapes import Drawing, Rect, String

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=42, leftMargin=42,
                                 topMargin=42, bottomMargin=42, title="SisaCare.AI analytics")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#173d35")
    styles["Heading2"].textColor = colors.HexColor("#176b50")
    paragraph = lambda text: Paragraph(escape(str(text)), styles["BodyText"])
    filters, metrics = data["filters"], data["metrics"]
    story = [Paragraph("SisaCare.AI | Administrative analytics", styles["Title"]), Spacer(1, 10),
             paragraph(f"Submission dates: {filters['start'] or 'All dates'} to {filters['end'] or 'All dates'} (UTC)"),
             paragraph(f"Generated: {data['generated_at']}"),
             paragraph(f"Source: {filters['provenance']} | Category: {filters['category'] or 'All'} | "
                       f"Status: {filters['status'] or 'All'} | Area: {filters['area'] or 'All'}"), Spacer(1, 14)]

    def table(rows, widths=None):
        result = Table([[paragraph(value) for value in row] for row in rows], colWidths=widths, hAlign="LEFT", repeatRows=1)
        result.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f2ed")),
                                    ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#d2ddd8")),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return result

    def shown(value, suffix=""):
        return "Unavailable" if value is None else f"{value}{suffix}"

    story += [Paragraph("Key metrics", styles["Heading2"]),
              table([["Metric", "Value"], ["Submitted reports", metrics["total_submitted"]],
                     ["Currently resolved", metrics["resolved_current"]],
                     ["Resolution rate", shown(metrics["resolution_rate_percent"], "%")],
                     ["Verified resolution durations", metrics["verified_resolution_count"]],
                     ["Average verified resolution", shown(metrics["average_resolution_hours"], " hours")],
                     ["Median verified resolution", shown(metrics["median_resolution_hours"], " hours")],
                     ["Staff task assignments", metrics["staff"]["task_assignments"]],
                     ["Active assignments", metrics["staff"]["active_assignments"]],
                     ["Verified completions with proof", metrics["staff"]["verified_completions_with_proof"]]]),
              Spacer(1, 12)]
    for heading, field in (("Reports by status", "by_status"), ("Reports by category", "by_category")):
        values = metrics[field]
        story += [Paragraph(heading, styles["Heading2"]),
                  table([["Name", "Reports"]] + [[name, count] for name, count in values.items()] if values else
                        [["Name", "Reports"], ["No data", 0]]), Spacer(1, 12)]
    trends = data["trends"][-12:]
    trend_heading = Paragraph("Reported and verified-resolved trend (latest 12 dates)", styles["Heading2"])
    if trends:
        drawing = Drawing(490, 120)
        peak = max(1, max(max(item["reported"], item["resolved"]) for item in trends))
        width = 470 / len(trends)
        for index, item in enumerate(trends):
            x = 10 + index * width
            drawing.add(Rect(x, 20, width * .32, 85 * item["reported"] / peak,
                             fillColor=colors.HexColor("#176b50"), strokeColor=None))
            drawing.add(Rect(x + width * .35, 20, width * .32, 85 * item["resolved"] / peak,
                             fillColor=colors.HexColor("#ea7c37"), strokeColor=None))
        drawing.add(String(10, 5, "Green: reported    Orange: verified resolved    Vertical scale: 0 to " + str(peak), fontSize=8))
        story += [KeepTogether([trend_heading, drawing,
                  table([["Date (UTC)", "Reported", "Resolved"]] +
                        [[item["date"], item["reported"], item["resolved"]] for item in trends])]), Spacer(1, 12)]
    else:
        story += [trend_heading, paragraph("No reports match the selected filters."), Spacer(1, 12)]
    story += [Paragraph("Definitions and data quality", styles["Heading2"]),
              paragraph("Resolution rate = currently resolved reports divided by submitted reports in the selected cohort. "
                        "No denominator yields unavailable."),
              paragraph("Resolution duration = pending-verification to resolved event time minus original submission time. "
                        "Only currently resolved reports with a valid verified event are included. "
                        "Average and median exclude unresolved or incomplete records."),
              paragraph("Reported trend groups the selected cohort by submission date; resolved trend groups verified "
                        "events for that cohort by event date, which may be after the selected submission range."),
              paragraph(f"Missing coordinates: {metrics['missing_coordinates']}; resolved without verified timestamp: "
                        f"{metrics['resolved_without_verified_timestamp']}. Grid density counts submitted reports, "
                        "not waste volume. Forecasts are a separate modeled layer.")]
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d2ddd8"))
        canvas.line(42, 34, A4[0] - 42, 34)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#52635c"))
        canvas.drawString(42, 22, "SisaCare.AI | Administrative analytics")
        canvas.drawRightString(A4[0] - 42, 22, f"Page {doc.page}")
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
