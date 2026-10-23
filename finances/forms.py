from django import forms
from .models import FinancialAccount, FinanceEntry


class AccountForm(forms.ModelForm):
    class Meta:
        model = FinancialAccount
        fields = ["name", "account_type", "institution", "opening_balance", "is_active"]


class EntryForm(forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = FinanceEntry
        fields = ["kind", "description", "amount", "date", "account"]

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        # only offer this club's accounts
        self.fields["account"].queryset = club.finance_accounts.all()
        self.fields["account"].required = False

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount