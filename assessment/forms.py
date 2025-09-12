from django import forms
from .models import Assessment

class TailwindFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring focus:border-blue-300'
            })

class AssessmentForm(TailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.coffee_purchase = kwargs.pop('coffee_purchase', None)
        super().__init__(*args, **kwargs)
        if self.coffee_purchase and not self.instance.pk:
            self.instance.coffee = self.coffee_purchase

        # Apply step increments
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.NumberInput):
                if name == "ref_price":
                    field.widget.attrs.update({"step": "50", "min": "0", "inputmode": "numeric"})
                else:
                    field.widget.attrs.update({"step": "0.1", "inputmode": "decimal"})

    class Meta:
        model = Assessment
        fields = [
            'moisture_content', 'group1_defects', 'group2_defects',
            'below_screen_12', 'pods', 'husks', 'stones', 'fm',
            'discretion', 'ref_price', 'offered_price'
        ]
        widgets = {
            'ref_price': forms.NumberInput(),
            'offered_price': forms.NumberInput(),
            'discretion': forms.NumberInput(),
            'moisture_content': forms.NumberInput(),
            'group1_defects': forms.NumberInput(),
            'group2_defects': forms.NumberInput(),
            'below_screen_12': forms.NumberInput(),
            'pods': forms.NumberInput(),
            'husks': forms.NumberInput(),
            'stones': forms.NumberInput(),
            'fm': forms.NumberInput(),
        }
