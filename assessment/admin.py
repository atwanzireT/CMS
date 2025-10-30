from django.contrib import admin
from django.db.models import Q
from .models import Assessment
from store.models import CoffeePurchase


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "coffee", "assessed_by", "decision",
        "clean_outturn", "derived_outturn", "final_price", "created_at"
    )
    list_filter = ("decision", "created_at")
    search_fields = ("coffee__supplier__name", "coffee__id")
    readonly_fields = ("clean_outturn", "derived_outturn", "final_price", "decision", "decision_reasons", "created_at")

    fieldsets = (
        ("Link", {
            "fields": ("coffee", "assessed_by")
        }),
        ("Inputs", {
            "fields": (
                "ref_price", "discretion",
                "moisture_content", "group1_defects", "group2_defects",
                "below_screen_12", "pods", "husks", "stones", "fm",
                "offered_price",
            )
        }),
        ("Computed / Decision", {
            "fields": ("clean_outturn", "derived_outturn", "final_price", "decision", "decision_reasons"),
        }),
        ("Meta", {
            "fields": ("created_at",),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """
        Restrict 'coffee' choices to purchases that don't already have an Assessment,
        plus the currently selected one when editing.
        """
        form = super().get_form(request, obj, **kwargs)
        already_assessed = CoffeePurchase.objects.filter(assessment__isnull=False)
        qs = CoffeePurchase.objects.all()

        if obj and obj.coffee_id:
            qs = qs.exclude(~Q(pk=obj.coffee_id) & Q(pk__in=already_assessed.values("pk")))
        else:
            qs = qs.exclude(pk__in=already_assessed.values("pk"))

        form.base_fields["coffee"].queryset = qs
        return form

    def save_model(self, request, obj, form, change):
        # Auto-attach the user who is recording the assessment if not set
        if not obj.assessed_by_id:
            obj.assessed_by = request.user
        super().save_model(request, obj, form, change)
