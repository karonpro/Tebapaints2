from django import forms
from .models import Customer, Payment, Expense, Transaction, SupplyHistory


# ---------------------------
# Customer Form
# ---------------------------
class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'location', 'tin', 'supply']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer Name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Physical Address'}),
            'location': forms.Select(attrs={'class': 'form-control'}),
            'tin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'TIN Number'}),
            'supply': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Supply Amount'}),
        }

# ---------------------------
# Payment Form
# ---------------------------



# ---------------------------
# Expense Form
# ---------------------------
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['name', 'notes', 'amount', 'location', 'date']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter expense name', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'location': forms.TextInput(attrs={'placeholder': 'Enter location', 'class': 'form-control'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


# ---------------------------
# Transaction Form
# ---------------------------
class TransactionForm(forms.ModelForm):
    total_sales = forms.DecimalField(label="Total Sales", required=False, disabled=True, decimal_places=2, max_digits=12)
    total_cashout = forms.DecimalField(label="Total Cashout", required=False, disabled=True, decimal_places=2, max_digits=12)
    difference = forms.DecimalField(label="Difference", required=False, disabled=True, decimal_places=2, max_digits=12)
    less_excess = forms.DecimalField(label="Less/Excess", required=False, disabled=True, decimal_places=2, max_digits=12)

    class Meta:
        model = Transaction
        fields = [
            'date', 'location', 'opening_balance', 'customer_balance',
            'paid', 'wholesale', 'debt', 'cash', 'accounts', 'expenses',
            'notes',
            'total_sales', 'total_cashout', 'difference', 'less_excess'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'customer_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'wholesale': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'debt': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'cash': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'accounts': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'expenses': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['total_sales'].initial = self.instance.total_sales
            self.fields['total_cashout'].initial = self.instance.total_cashout
            self.fields['difference'].initial = self.instance.difference
            self.fields['less_excess'].initial = self.instance.less_excess


# ---------------------------
# Add Supply Form
# ---------------------------
from django import forms
from .models import SupplyHistory
from django.utils import timezone

class SupplyForm(forms.ModelForm):
    class Meta:
        model = SupplyHistory
        fields = ['amount', 'notes', 'date']  # include date so it is editable
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter amount'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'}),
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }


    

    class Meta:
        model = SupplyHistory
        fields = ['amount', 'date', 'notes']  # include date here
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

from django import forms
from .models import BalanceAdjustment

class BalanceAdjustmentForm(forms.ModelForm):
    class Meta:
        model = BalanceAdjustment
        fields = ['amount', 'notes', 'reference']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': 'Enter amount'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this adjustment...'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional reference number...'
            }),
        }
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount
    

    from django import forms
from .models import Customer

class DebtForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    reference = forms.CharField(max_length=100, required=False)

class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    reference = forms.CharField(max_length=100, required=False)

class BalanceAdjustmentForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    reference = forms.CharField(max_length=100, required=False)