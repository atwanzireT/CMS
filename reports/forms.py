from django import forms
from .models import DailyStoreReport, CoffeeType

class GeneralReportFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        })
    )
    date_to = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        })
    )
    coffee_type = forms.ChoiceField(
        required=False,
        choices=[("", "All types")] + list(CoffeeType.choices),
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        })
    )
    q = forms.CharField(
        required=False, 
        help_text="Search buyer or comments",
        widget=forms.TextInput(attrs={
            "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
            "placeholder": "Search buyer or comments..."
        })
    )


class DailyStoreReportForm(forms.ModelForm):
    class Meta:
        model = DailyStoreReport
        fields = [
            "date", "coffee_type",
            "average_buying_price_ugx_per_kg",
            "kilograms_bought", "kilograms_sold",
            "number_of_bags_sold",
            "bags_left_in_store", "kilograms_left_in_store",
            "kilograms_unbought_in_store",
            "sold_to", "advances_given_ugx",
            "attachment", "comments",
        ]
        widgets = {
            "date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            }),
            "coffee_type": forms.Select(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            }),
            "average_buying_price_ugx_per_kg": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "kilograms_bought": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "kilograms_sold": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "number_of_bags_sold": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "min": "0"
            }),
            "bags_left_in_store": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "min": "0"
            }),
            "kilograms_left_in_store": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "kilograms_unbought_in_store": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "sold_to": forms.TextInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "placeholder": "Enter buyer name..."
            }),
            "advances_given_ugx": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "step": "0.01",
                "min": "0"
            }),
            "attachment": forms.FileInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            }),
            "comments": forms.Textarea(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "rows": 4,
                "placeholder": "Add any additional comments..."
            }),
        }