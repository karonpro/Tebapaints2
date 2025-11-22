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
# ---------------------------
# Transaction Form - FIXED VERSION
# ---------------------------
class TransactionForm(forms.ModelForm):
    # These are display-only fields that use @property methods from the model
    total_sales = forms.DecimalField(
        label="Total Sales", 
        required=False, 
        disabled=True, 
        decimal_places=2, 
        max_digits=12,
        widget=forms.NumberInput(attrs={'class': 'form-control bg-light', 'readonly': 'readonly'})
    )
    total_cashout = forms.DecimalField(
        label="Total Cashout", 
        required=False, 
        disabled=True, 
        decimal_places=2, 
        max_digits=12,
        widget=forms.NumberInput(attrs={'class': 'form-control bg-light', 'readonly': 'readonly'})
    )
    difference = forms.DecimalField(
        label="Difference", 
        required=False, 
        disabled=True, 
        decimal_places=2, 
        max_digits=12,
        widget=forms.NumberInput(attrs={'class': 'form-control bg-light', 'readonly': 'readonly'})
    )
    less_excess = forms.DecimalField(
        label="Less/Excess", 
        required=False, 
        disabled=True, 
        decimal_places=2, 
        max_digits=12,
        widget=forms.NumberInput(attrs={'class': 'form-control bg-light', 'readonly': 'readonly'})
    )

    class Meta:
        model = Transaction
        fields = [
            'date', 'location', 'opening_balance', 'customer_balance',
            'paid', 'wholesale', 'debt', 'cash', 'accounts', 'expenses',
            'notes'
            # NOTE: Remove computed fields from this list - they're @property methods
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
        
        # Calculate initial values for display fields using the same logic as @property methods
        opening = float(self.initial.get('opening_balance', 0) or 0)
        customer = float(self.initial.get('customer_balance', 0) or 0)
        paid = float(self.initial.get('paid', 0) or 0)
        wholesale = float(self.initial.get('wholesale', 0) or 0)
        debt = float(self.initial.get('debt', 0) or 0)
        cash = float(self.initial.get('cash', 0) or 0)
        accounts = float(self.initial.get('accounts', 0) or 0)
        expenses = float(self.initial.get('expenses', 0) or 0)
        
        # Use the same calculation logic as your @property methods
        total_sales = customer + paid + wholesale
        total_cashout = debt + cash + accounts + expenses
        difference = total_sales - total_cashout
        less_excess = difference - opening
        
        # Set initial values for display fields
        self.fields['total_sales'].initial = total_sales
        self.fields['total_cashout'].initial = total_cashout
        self.fields['difference'].initial = difference
        self.fields['less_excess'].initial = less_excess

    def clean(self):
        """Calculate computed values for display in the template if needed"""
        cleaned_data = super().clean()
        
        # These calculations are just for display - the @property methods handle the real calculations
        opening = cleaned_data.get('opening_balance', 0) or 0
        customer = cleaned_data.get('customer_balance', 0) or 0
        paid = cleaned_data.get('paid', 0) or 0
        wholesale = cleaned_data.get('wholesale', 0) or 0
        debt = cleaned_data.get('debt', 0) or 0
        cash = cleaned_data.get('cash', 0) or 0
        accounts = cleaned_data.get('accounts', 0) or 0
        expenses = cleaned_data.get('expenses', 0) or 0
        
        # Update form instance with calculated values for display
        self.fields['total_sales'].initial = customer + paid + wholesale
        self.fields['total_cashout'].initial = debt + cash + accounts + expenses
        self.fields['difference'].initial = self.fields['total_sales'].initial - self.fields['total_cashout'].initial
        self.fields['less_excess'].initial = self.fields['difference'].initial - opening
        
        return cleaned_data

    # Remove the save() method override since @property methods handle the calculations
    # The computed fields are calculated automatically when accessed
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