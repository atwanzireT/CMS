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
        # Capture coffee_purchase from kwargs
        self.coffee_purchase = kwargs.pop('coffee_purchase', None)
        super().__init__(*args, **kwargs)

        # Assign coffee to instance early, before clean() runs
        if self.coffee_purchase and not self.instance.pk:
            self.instance.coffee = self.coffee_purchase

    class Meta:
        model = Assessment
        fields = [
            'moisture_content', 'group1_defects', 'group2_defects',
            'below_screen_12', 'pods', 'husks', 'stones', 'fm',
            'discretion', 'ref_price', 'offered_price'
        ]
        widgets = {
            'offered_price': forms.TextInput(attrs={'class': 'block w-full px-3 py-2 border rounded'}),
        }
