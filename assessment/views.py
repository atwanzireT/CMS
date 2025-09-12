from __future__ import annotations
import io
import logging
import traceback
from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepInFrame
)
from .forms import AssessmentForm
from .models import Assessment
from store.models import CoffeePurchase

logger = logging.getLogger(__name__)

# -------------------- Decimal helpers (UI-safe) --------------------

D0   = Decimal("0")
D01  = Decimal("0.1")
D001 = Decimal("0.01")

def to_decimal(x) -> Decimal:
    """Coerce any numeric-like value to Decimal reliably."""
    if isinstance(x, Decimal):
        return x
    if x is None:
        return D0
    try:
        return Decimal(str(x))
    except Exception:
        return D0

def q1(x) -> Decimal:
    """Quantize to 1 dp (for percentages & final price storage/display)."""
    return to_decimal(x).quantize(D01, rounding=ROUND_HALF_UP)

def q2(x) -> Decimal:
    """Quantize to 2 dp (only for percentage displays if ever needed)."""
    return to_decimal(x).quantize(D001, rounding=ROUND_HALF_UP)

# -------------------- Views --------------------

@login_required
def assessment_list(request):
    """
    Dashboard list:
    - totals (completed, pending, rejected, % rejected)
    - lists of assessed & unassessed purchases
    """
    # Prefetch relationships for template efficiency
    assessments_qs = Assessment.objects.select_related(
        "coffee",
        "coffee__supplier",
        "assessed_by",
    )

    total_assessments = assessments_qs.count()
    rejected_count = assessments_qs.filter(decision="Rejected").count()
    rejection_rate = q1((to_decimal(rejected_count) / total_assessments * 100) if total_assessments else D0)

    # Pending purchases (need assessment)
    pending_qs = CoffeePurchase.objects.filter(
        assessment_needed=True,
        assessment__isnull=True,
    )

    assessed_purchases = (
        CoffeePurchase.objects
        .filter(assessment__isnull=False)
        .select_related("supplier", "assessment")
        .order_by("-purchase_date")
    )

    unassessed_purchases = (
        pending_qs
        .select_related("supplier")
        .order_by("-purchase_date")
    )

    totals = {
        "total_assessments": total_assessments,
        "completed_count": total_assessments,
        "pending_count": pending_qs.count(),
        "rejected_count": rejected_count,
        "rejection_rate": rejection_rate,  # Decimal 1dp
    }

    context = {
        "totals": totals,
        "assessed_purchases": assessed_purchases,
        "unassessed_purchases": unassessed_purchases,
        "assessments": assessments_qs,  # if your template iterates this
    }
    return render(request, "assessment_list.html", context)


@login_required
def assessment_create(request, pk: int):
    """
    Create or update the single Assessment for a CoffeePurchase.
    - Binds coffee on create
    - Saves inside an atomic transaction
    - Surfaces validation errors and (optionally) stack traces for staff
    """
    coffee_purchase = get_object_or_404(
        CoffeePurchase.objects.select_related("supplier"),
        pk=pk,
    )

    # Find or create in-memory assessment
    assessment, created = Assessment.objects.select_related(
        "coffee", "assessed_by"
    ).filter(coffee=coffee_purchase).first(), False
    if assessment is None:
        assessment = Assessment(assessed_by=request.user)  # coffee will be set by form
        created = True

    if request.method == "POST":
        form = AssessmentForm(request.POST, instance=assessment, coffee_purchase=coffee_purchase)

        if not form.is_valid():
            # Surface form errors to the user
            messages.error(
                request,
                mark_safe(
                    "<strong>Validation Error</strong>"
                    f"<div class='mt-2 text-sm'>{form.errors.as_ul()}</div>"
                ),
            )
        else:
            try:
                with transaction.atomic():
                    assessment = form.save(commit=False)
                    assessment.assessed_by = request.user
                    # coffee is bound in the form's __init__ when creating
                    assessment.save()  # triggers post_save signals

                    # Once assessed, mark purchase flag off (idempotent)
                    if coffee_purchase.assessment_needed:
                        coffee_purchase.assessment_needed = False
                        coffee_purchase.save(update_fields=["assessment_needed"])

                messages.success(request, "Quality assessment saved successfully!")
                return redirect("assessment_list")

            except Exception as e:
                # Log full traceback server-side
                logger.exception("Error saving assessment for CoffeePurchase id=%s", coffee_purchase.pk)

                # Show rich error to staff; minimal to others
                if request.user.is_staff:
                    tb = traceback.format_exc()
                    messages.error(
                        request,
                        mark_safe(
                            "<strong>Unexpected Error</strong>"
                            f"<div class='mt-2 text-sm'>"
                            f"<div><b>Message:</b> {escape(str(e))}</div>"
                            "<details open class='mt-2'>"
                            "<summary class='cursor-pointer text-red-700'>Traceback</summary>"
                            f"<pre class='mt-2 whitespace-pre-wrap text-xs bg-red-50 p-3 rounded-lg border'>{escape(tb)}</pre>"
                            "</details>"
                            "</div>"
                        ),
                    )
                else:
                    messages.error(request, "An unexpected error occurred while saving. Please try again or contact an admin.")
    else:
        form = AssessmentForm(instance=assessment, coffee_purchase=coffee_purchase)

    context = {
        "form": form,
        "coffee_purchase": coffee_purchase,
        "page_title": f"Quality Assessment - {coffee_purchase}",
        "form_title": "Create Assessment" if created else "Update Assessment",
    }
    return render(request, "assessment_form.html", context)


@login_required
def assessment_detail(request, pk: int):
    """
    Detailed single-assessment view.
    Uses model-computed fields (final_price, decision, decision_reasons).
    Adds UI-quantized numbers to 1 dp for consistency with storage.
    """
    assessment = get_object_or_404(
        Assessment.objects.select_related("coffee", "coffee__supplier", "assessed_by"),
        pk=pk,
    )

    is_rejected = (assessment.decision == "Rejected")
    rejection_reason = assessment.decision_reasons or None

    final_price = q1(assessment.final_price or D0)
    ref_price   = q1(assessment.ref_price   or D0)
    diff        = q1(final_price - ref_price) if ref_price else D0
    pct         = q1((diff / ref_price * 100) if ref_price else D0)

    context = {
        "assessment": assessment,
        "is_rejected": is_rejected,
        "rejection_reason": rejection_reason,
        "price_analysis": {
            "final_price": final_price,
            "reference_price": ref_price,
            "difference": diff,
            "percentage": pct,
        },
        "page_title": f"Assessment - {assessment.coffee}",
    }
    return render(request, "assessment_detail.html", context)


# ---------- Helpers ----------
def fmt_money(x):
    if x is None:
        return "—"
    try:
        return f"{Decimal(x):,.0f}"
    except Exception:
        return str(x)

def fmt_qty(x):
    if x is None:
        return "—"
    try:
        return f"{Decimal(x):,.0f}"
    except Exception:
        return str(x)

def get_logo_flowable():
    """Load logo from staticfiles storage with constrained size (no HTTP)."""
    path = finders.find("assets/images/logos/logo-dark.png")  # adjust if needed
    if not path:
        return Spacer(32*mm, 12*mm)
    try:
        return Image(path, width=32*mm, height=12*mm, kind="proportional")
    except Exception:
        return Spacer(32*mm, 12*mm)

def draw_header_footer(canvas, doc):
    width, height = A4
    canvas.saveState()
    # Header rule
    canvas.setStrokeColorRGB(0.82, 0.87, 0.94)
    canvas.setLineWidth(0.7)
    canvas.line(15*mm, height - 15*mm, width - 15*mm, height - 15*mm)
    # Footer
    footer_y = 12 * mm
    canvas.setFont("Helvetica", 9)
    canvas.setFillColorRGB(0.4, 0.4, 0.4)
    canvas.drawString(15*mm, footer_y, "Generated by Great Pearl Coffee Factory Management System")
    page_label = f"Page {canvas.getPageNumber()}"
    w = canvas.stringWidth(page_label, "Helvetica", 9)
    canvas.drawString(width - 15*mm - w, footer_y, page_label)
    canvas.restoreState()


def assessment_pdf(request, pk):
    assessment = Assessment.objects.select_related("coffee__supplier").get(pk=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14*mm,
        rightMargin=14*mm,
        topMargin=20*mm,
        bottomMargin=18*mm,
        title=f"Assessment {assessment.pk}",
    )

    # Styles
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=base["Title"], fontName="Helvetica-Bold",
                        fontSize=16, leading=19, alignment=1, spaceAfter=6)
    subtitle = ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=10.5,
                              leading=13, textColor=colors.HexColor("#4b5563"), alignment=1)
    small = ParagraphStyle("Small", parent=base["Normal"], fontSize=9.5,
                           leading=12, textColor=colors.HexColor("#4b5563"))
    label = ParagraphStyle("Label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10.5)
    section = ParagraphStyle("Section", parent=base["Heading3"], fontName="Helvetica-Bold",
                             fontSize=12, leading=14, textColor=colors.HexColor("#111827"),
                             spaceBefore=8, spaceAfter=4)
    right = ParagraphStyle("Right", parent=base["Normal"], alignment=2)
    right_big = ParagraphStyle("RightBig", parent=base["Normal"], alignment=2, fontSize=11)

    elements = []

    # ---------- Brand header (KeepInFrame inside Table cell) ----------
    logo_img = get_logo_flowable()
    brand_lines = [
        Paragraph("<b>GREAT PEARL COFFEE FACTORY</b>", ParagraphStyle(
            "BrandName", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=13)),
        Paragraph("Specialty Coffee Processing &amp; Export", small),
        Paragraph("Tel: +256 781 121 639 / +256 778 536 681 • www.greatpearlcoffee.com • greatpearlcoffee@gmail.com", small),
        Paragraph("Uganda Coffee Development Authority Licensed", small),
    ]
    # Make sure the text block fits the header row; shrink if needed.
    brand_block = KeepInFrame(maxWidth=(doc.width - 38*mm), maxHeight=16*mm,
                              content=brand_lines, hAlign='LEFT', vAlign='MIDDLE', mode='shrink')

    brand_table = Table(
        [[logo_img, brand_block]],
        colWidths=[38*mm, None],
        rowHeights=[16*mm],  # a little taller to breathe
        style=TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 0),
        ])
    )
    elements.append(brand_table)
    elements.append(Spacer(1, 4))

    # Title band
    elements.append(Paragraph("QUALITY ASSESSMENT REPORT", h1))
    meta_line = f"Document No: ASMT-{assessment.pk} &nbsp;&nbsp;|&nbsp;&nbsp; Date: {assessment.created_at.strftime('%d/%m/%Y')}"
    elements.append(Paragraph(meta_line, subtitle))
    elements.append(Spacer(1, 8))

    # ---------- Meta table (NO Discretion) ----------
    qty = assessment.coffee.quantity
    meta_data = [
        [Paragraph("Supplier", label), assessment.coffee.supplier.name,
         Paragraph("Phone", label), assessment.coffee.supplier.phone or "—"],
        [Paragraph("Coffee Type", label), assessment.coffee.get_coffee_type_display(),
         Paragraph("Form", label), assessment.coffee.get_coffee_category_display()],
        [Paragraph("Quantity (kg)", label), Paragraph(fmt_qty(qty), right),
         Paragraph("Purchase Date", label), assessment.coffee.purchase_date.strftime("%d/%m/%Y")],
        [Paragraph("Reference Price (UGX)", label), Paragraph(fmt_money(assessment.ref_price), right),
         "", ""],  # keep 4 columns alignment
    ]
    meta_table = Table(meta_data, colWidths=[40*mm, 65*mm, 40*mm, None])
    meta_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#94a3b8")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (1,0), (1,-1), "LEFT"),
        ("ALIGN", (3,0), (3,-1), "LEFT"),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8))

    # ---------- Quality Parameters ----------
    elements.append(Paragraph("Quality Assessment Parameters", section))
    qp_data = [
        [Paragraph("Parameter", label), Paragraph("Value", label), Paragraph("Unit", label),
         Paragraph("Parameter", label), Paragraph("Value", label), Paragraph("Unit", label)],
        ["Moisture", f"{assessment.moisture_content}", "%", "Group 1 Defects", f"{assessment.group1_defects}", "%"],
        ["Group 2 Defects", f"{assessment.group2_defects}", "%", "Below Screen 12", f"{assessment.below_screen_12}", "%"],
        ["Pods", f"{assessment.pods}", "%", "Husks", f"{assessment.husks}", "%"],
        ["Stones", f"{assessment.stones}", "%", "FM (P+H+S)", f"{assessment.fm}", "%"],
        ["Clean Outturn", f"{assessment.clean_outturn}", "%", "Derived Outturn", f"{assessment.derived_outturn}", "%"],
    ]
    qp_table = Table(qp_data, colWidths=[34*mm, 22*mm, 16*mm, 34*mm, 22*mm, 16*mm])
    qp_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#94a3b8")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e2e8f0")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("ALIGN", (4,1), (4,-1), "RIGHT"),
        ("ALIGN", (2,1), (2,-1), "CENTER"),
        ("ALIGN", (5,1), (5,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    elements.append(qp_table)
    elements.append(Spacer(1, 8))

    # ---------- Decision & Pricing (Price=offered_price; add Total; NO Final Price) ----------
    price = assessment.offered_price
    total = (price * Decimal(qty)) if (price is not None and qty is not None) else None
    status = "REJECTED" if assessment.is_rejected else "ACCEPTED"

    dp_rows = [
        [Paragraph("Status", label), Paragraph(
            f'<font color="{ "#9b1c1c" if assessment.is_rejected else "#066e3c"}"><b>{status}</b></font>',
            base["Normal"]
        )],
        [Paragraph("Price (UGX)", label), Paragraph(fmt_money(price), right)],
        [Paragraph("Quantity (kg)", label), Paragraph(fmt_qty(qty), right)],
        [Paragraph("<b>TOTAL (UGX)</b>", ParagraphStyle("LabelBig", parent=label, fontSize=11)),
         Paragraph(f"<b>{fmt_money(total)}</b>", right_big)],
    ]
    dp_table = Table(dp_rows, colWidths=[50*mm, None])
    dp_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#94a3b8")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.white, colors.HexColor("#f8fafc")]),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#eef2ff")),  # highlight TOTAL
    ]))
    elements.append(dp_table)

    if assessment.decision_reasons:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Notes:</b> " + assessment.decision_reasons.replace("\n", "<br/>"), small))

    # ---------- Purchase Notes ----------
    if assessment.coffee.notes:
        elements.append(Spacer(1, 8))
        notes_tbl = Table(
            [[Paragraph("<b>Purchase Notes</b>", label)],
             [Paragraph(assessment.coffee.notes, base["Normal"])]],
            colWidths=[None],
            style=TableStyle([
                ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#94a3b8")),
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
                ("RIGHTPADDING", (0,0), (-1,-1), 8),
                ("TOPPADDING", (0,0), (-1,-1), 6),
                ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ])
        )
        elements.append(notes_tbl)

    elements.append(Spacer(1, 14))

    # ---------- Signatures ----------
    sig = Table(
        [["", ""],
         ["Store Keeper — Signature & Date", "Quality Analyst — Signature & Date"]],
        colWidths=[None, None],
        rowHeights=[18*mm, None],
        style=TableStyle([
            ("LINEABOVE", (0,0), (0,0), 0.8, colors.black),
            ("LINEABOVE", (1,0), (1,0), 0.8, colors.black),
            ("ALIGN", (0,1), (-1,1), "CENTER"),
            ("TEXTCOLOR", (0,1), (-1,1), colors.HexColor("#4b5563")),
        ])
    )
    elements.append(sig)

    # Build PDF with header/footer on every page
    doc.build(elements, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)

    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"Assessment-{assessment.pk}.pdf")
