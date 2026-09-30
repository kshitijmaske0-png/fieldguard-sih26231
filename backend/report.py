import io
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

RESULT_COLOURS = {"POSITIVE": "#b00020", "NEGATIVE": "#1b7f3b", "INCONCLUSIVE": "#8a6d00"}


def _qr(url, size_mm=34):
    w = QrCodeWidget(url)
    x0, y0, x1, y1 = w.getBounds()
    s = size_mm * mm
    d = Drawing(s, s, transform=[s / (x1 - x0), 0, 0, s / (y1 - y0), 0, 0])
    d.add(w)
    return d


def build_pdf(rec, verify_url, valid, image_path=None, annotated_path=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"FieldGuard record {rec['id']}")
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=8, leading=10)
    story = [Paragraph("FieldGuard test record", st["Title"]),
             Paragraph("<b>Presumptive result.</b> This is a colour-match reading. Laboratory confirmation is required.", st["BodyText"]),
             Spacer(1, 6)]
    colour = RESULT_COLOURS.get(rec["result"], "#333333")
    story.append(Paragraph(f'<font size="20" color="{colour}"><b>{rec["result"]}</b></font> '
                           f'&nbsp; match score {rec["match_score"]:.2f} (not a probability)', st["BodyText"]))
    story.append(Spacer(1, 8))
    gps = rec.get("gps") or {}
    gps_txt = f'{gps.get("lat")}, {gps.get("lng")} (±{gps.get("accuracy")} m)' if gps else "not available"
    steps = rec.get("protocol_steps", {})
    rows = [["Record ID", rec["id"]], ["Server time (UTC)", rec["server_time_utc"]],
            ["Device time (unverified)", rec.get("client_time") or "-"], ["Operator", rec["operator_id"]],
            ["Device", rec["device_id"]], ["GPS (metadata, can be spoofed)", gps_txt],
            ["Kit / lot / expiry", f'{rec["kit_type"]} / {rec["kit_lot"]} / {rec["kit_expiry"]}'],
            ["Control done / timer", f'{steps.get("control_done")} / {steps.get("timer_seconds")} s'],
            ["Colour distances (dE2000)", ", ".join(f"{k}: {v}" for k, v in rec["colour_scores"].items())],
            ["Chart version", rec["chart_version"]], ["Image SHA-256", rec["image_sha256"]],
            ["Previous record hash", rec["prev_hash"]], ["Record hash", rec["record_hash"]],
            ["Signature (Ed25519)", rec["signature"]]]
    t = Table([[Paragraph(f"<b>{a}</b>", small), Paragraph(str(b), small)] for a, b in rows], colWidths=[48 * mm, 126 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 10)]
    imgs = []
    for p in (image_path, annotated_path):
        if p and Path(p).exists():
            try:
                imgs.append(Image(str(p), width=82 * mm, height=62 * mm, kind="proportional"))
            except Exception:
                pass
    if imgs:
        story += [Table([imgs], colWidths=[87 * mm] * len(imgs)), Spacer(1, 8)]
    status = "VALID at time of download" if valid else "INVALID: this record failed verification"
    story.append(KeepTogether([
        Table([[_qr(verify_url), Paragraph(f"<b>Verify online</b><br/>Scan the QR code or open:<br/>{verify_url}<br/><br/>"
                                           f"<b>{status}</b>", small)]], colWidths=[40 * mm, 130 * mm]),
        Paragraph("Tamper-evident means changes are detectable, not impossible. GPS and device time are metadata.", small)]))
    doc.build(story)
    return buf.getvalue()
