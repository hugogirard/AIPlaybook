"""
Generate invoice PDFs for Contoso TCG (vintage & legacy Magic cards).
Requirements: pip install reportlab
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import locale
import os

# Try to set locale for currency formatting; fallback to plain formatting
try:
    locale.setlocale(locale.LC_ALL, '')
except Exception:
    pass


def moneyfmt(amount):
    """Return a formatted currency string for amount (float/Decimal)."""
    try:
        amt = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        raise ValueError("Amount must be numeric")
    try:
        # locale.currency may fail on some platforms; fallback
        return locale.currency(float(amt), grouping=True)
    except Exception:
        return f"${amt:,}"


def compute_totals(items, tax_rate=0.0):
    subtotal = Decimal('0.00')
    for it in items:
        qty = Decimal(str(it.get('qty', 0)))
        unit = Decimal(str(it.get('unit_price', '0.00')))
        line = (qty * unit).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        it['_line_total'] = line
        subtotal += line
    subtotal = subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tax = (subtotal * Decimal(str(tax_rate))
           ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return subtotal, tax, total


def validate_invoice_data(data):
    required = ['invoice_number', 'date', 'bill_to', 'items']
    for k in required:
        if k not in data:
            raise ValueError(f"Missing required invoice field: {k}")
    if not isinstance(data['items'], list):
        raise ValueError("items must be a list")
    # minimal normalization
    data.setdefault('tax_rate', 0.0)
    data.setdefault('due_date', None)
    data.setdefault('notes', '')
    return data


def generate_invoice(invoice_data, filename):
    """
    Generate a PDF invoice.
    invoice_data (dict) fields:
      - invoice_number (str)
      - date (str or datetime)
      - due_date (str or datetime, optional)
      - bill_to (dict) with 'name' and optional 'address' (string or list)
      - items (list of dict): each item: description (str), qty (int), unit_price (number)
      - tax_rate (float 0.0-1.0)
      - notes (str)
    filename: path where PDF will be written
    """
    invoice_data = validate_invoice_data(invoice_data)
    # prepare
    items = invoice_data['items']
    tax_rate = invoice_data.get('tax_rate', 0.0)
    subtotal, tax, total = compute_totals(items, tax_rate)

    # Document setup
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    heading = ParagraphStyle(
        'Heading', parent=styles['Heading1'], fontSize=18, spaceAfter=6)
    small = ParagraphStyle('Small', parent=normal, fontSize=9)

    story = []

    # Header: Company name and invoice metadata
    story.append(Paragraph("Contoso TCG", heading))
    story.append(
        Paragraph("Vintage & Legacy Magic: cards, singles, graded", normal))
    story.append(Spacer(1, 6))

    meta_table_data = [
        ["Invoice #:", invoice_data['invoice_number'],
            "Date:", _fmt_date(invoice_data.get('date'))],
    ]
    if invoice_data.get('due_date'):
        meta_table_data.append(
            ["Due Date:", _fmt_date(invoice_data.get('due_date')), "", ""])

    meta_table = Table(meta_table_data, colWidths=[30*mm, 60*mm, 20*mm, 40*mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # Bill To
    bill_to = invoice_data['bill_to']
    bill_lines = []
    name = bill_to.get('name', '')
    if name:
        bill_lines.append(name)
    addr = bill_to.get('address', '')
    if isinstance(addr, (list, tuple)):
        bill_lines.extend(addr)
    elif addr:
        bill_lines.append(addr)
    bill_para = Paragraph("<br />".join(bill_lines), normal)
    story.append(Paragraph("<b>Bill To:</b>", normal))
    story.append(bill_para)
    story.append(Spacer(1, 12))

    # Items table
    table_data = [["Description", "Qty", "Unit price", "Line total"]]
    for it in items:
        desc = it.get('description', '')
        qty = it.get('qty', 0)
        unit = it.get('unit_price', 0)
        line_total = it.get('_line_total', None)
        if line_total is None:
            # compute if missing
            line_total = Decimal(str(qty)) * Decimal(str(unit))
        table_data.append([Paragraph(desc, normal), str(
            qty), moneyfmt(unit), moneyfmt(line_total)])

    # Totals rows
    table_data.append(["", "", "Subtotal:", moneyfmt(subtotal)])
    table_data.append(["", "", f"Tax ({tax_rate*100:.1f}%):", moneyfmt(tax)])
    table_data.append(["", "", "<b>Total:</b>", f"<b>{moneyfmt(total)}</b>"])

    colWidths = [100*mm, 20*mm, 35*mm, 35*mm]
    tbl = Table(table_data, colWidths=colWidths, hAlign='LEFT')
    tbl_style = TableStyle([
        ('GRID', (0, 0), (-1, -4), 0.25, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (3, -1), 'RIGHT'),
        ('SPAN', (0, -3), (2, -3)),
        ('SPAN', (0, -2), (2, -2)),
        ('SPAN', (0, -1), (2, -1)),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
    ])
    tbl.setStyle(tbl_style)
    story.append(tbl)
    story.append(Spacer(1, 12))

    # Notes & footer
    notes = invoice_data.get('notes', '')
    if notes:
        story.append(Paragraph("<b>Notes</b>", normal))
        story.append(Paragraph(notes, small))
        story.append(Spacer(1, 6))

    story.append(Paragraph(
        "Contoso TCG — Thank you for buying vintage & legacy Magic cards!", small))
    story.append(
        Paragraph("Contact: sales@contosotcg.example | www.contosotcg.example", small))

    # Build
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    doc.build(story)


def _fmt_date(d):
    if not d:
        return ''
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    return str(d)


if __name__ == "__main__":
    # Example usage: run this file to generate a demo invoice
    demo = {
        "invoice_number": "CTCG-2025-0001",
        "date": datetime.today().date().isoformat(),
        "due_date": (datetime.today()).date().isoformat(),
        "bill_to": {
            "name": "Ms. Jane Doe",
            "address": ["742 Evergreen Terrace", "Springfield, USA"]
        },
        "items": [
            {"description": "Black Lotus (Alpha) — Vintage",
             "qty": 1, "unit_price": 125000.00},
            {"description": "Tarmogoyf (Legacy playset) — set of 4",
             "qty": 4, "unit_price": 200.00},
            {"description": "Force of Will (Legacy) — single",
             "qty": 1, "unit_price": 450.00},
        ],
        "tax_rate": 0.00,
        "notes": "Payment via bank transfer. All cards sold as-is. Contact us for shipping options."
    }
    out = os.path.join(os.path.dirname(__file__), "invoice_demo.pdf")
    print(f"Generating demo invoice -> {out}")
    generate_invoice(demo, out)
    print("Done.")
