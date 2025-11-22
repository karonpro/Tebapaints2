import json
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Product, ProductStock, RetailSale, RetailStock, Sale, SaleItem, Payment
from core.models import Location
from transactions.models import Customer

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'sku', 'cost_price', 'selling_price', 'reorder_level']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class ProductStockForm(forms.ModelForm):
    class Meta:
        model = ProductStock
        fields = ['product', 'location', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location

class RetailSaleForm(forms.ModelForm):
    current_stock = forms.DecimalField(
        required=False,
        decimal_places=2,
        disabled=True,
        label="Available Stock",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly'
        })
    )
    
    class Meta:
        model = RetailSale
        fields = ['product', 'location', 'amount_given', 'unit_price', 'current_stock']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Select a product...'
            }),
            'location': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Select a location...'
            }),
            'amount_given': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'form-control',
                'placeholder': '0.00'
            }),
            'unit_price': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'form-control',
                'placeholder': '0.00'
            }),
        }
        labels = {
            'amount_given': 'Amount Received',
            'unit_price': 'Price Per Unit',
        }
        help_texts = {
            'amount_given': 'Enter the amount of money received from customer',
            'unit_price': 'Current selling price per unit/liter',
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Use all products since there's no is_active field
        self.fields['product'].queryset = Product.objects.all()
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location
        
        # Set initial current_stock value if instance exists
        if self.instance and self.instance.pk:
            try:
                stock = ProductStock.objects.get(
                    product=self.instance.product,
                    location=self.instance.location
                )
                self.fields['current_stock'].initial = stock.quantity
            except ProductStock.DoesNotExist:
                self.fields['current_stock'].initial = 0

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        location = cleaned_data.get('location')
        amount_given = cleaned_data.get('amount_given')
        unit_price = cleaned_data.get('unit_price')

        # Validate that product and location are selected
        if product and location:
            try:
                # Check if main stock exists
                main_stock = ProductStock.objects.get(product=product, location=location)
                
                # Calculate required quantity
                if amount_given and unit_price and unit_price > 0:
                    quantity_needed = amount_given / unit_price
                    
                    # Check stock availability
                    if main_stock.quantity < quantity_needed:
                        available = main_stock.quantity
                        self.add_error(
                            'amount_given',
                            f"Insufficient stock. Available: {available:.2f} units. "
                            f"Required: {quantity_needed:.2f} units for ${amount_given:.2f}"
                        )
                        
                        # Update current_stock field for display
                        self.fields['current_stock'].initial = available
                
                # Set current stock value for display
                self.cleaned_data['current_stock'] = main_stock.quantity
                
            except ProductStock.DoesNotExist:
                self.add_error('product', "No stock available for this product at selected location")
                self.cleaned_data['current_stock'] = 0

        # Validate amount and unit price
        if amount_given and amount_given <= 0:
            self.add_error('amount_given', "Amount must be greater than 0")
        
        if unit_price and unit_price <= 0:
            self.add_error('unit_price', "Unit price must be greater than 0")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set the sold_by user
        if self.user:
            instance.sold_by = self.user
        
        # Calculate quantity_given
        if instance.amount_given and instance.unit_price:
            instance.quantity_given = instance.amount_given / instance.unit_price
        
        if commit:
            instance.save()
        
        return instance

class RetailStockTransferForm(forms.Form):
    """Form for transferring stock between main inventory and retail"""
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'step': '0.01',
            'class': 'form-control',
            'placeholder': 'Quantity to transfer'
        })
    )
    transfer_type = forms.ChoiceField(
        choices=[
            ('TO_RETAIL', 'Transfer to Retail'),
            ('TO_MAIN', 'Return to Main Inventory')
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        location = cleaned_data.get('location')
        quantity = cleaned_data.get('quantity')
        transfer_type = cleaned_data.get('transfer_type')

        if product and location and quantity:
            try:
                main_stock = ProductStock.objects.get(product=product, location=location)
                retail_stock, _ = RetailStock.objects.get_or_create(
                    product=product, location=location
                )

                if transfer_type == 'TO_RETAIL' and main_stock.quantity < quantity:
                    self.add_error(
                        'quantity',
                        f"Not enough stock in main inventory. Available: {main_stock.quantity}"
                    )
                elif transfer_type == 'TO_MAIN' and retail_stock.quantity < quantity:
                    self.add_error(
                        'quantity',
                        f"Not enough stock in retail. Available: {retail_stock.quantity}"
                    )

            except ProductStock.DoesNotExist:
                self.add_error('product', "No stock available for this product at selected location")

        return cleaned_data

class SaleForm(forms.ModelForm):
    items_data = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'id_items_data'}),
        required=False,
        initial='[]'
    )
    
    class Meta:
        model = Sale
        fields = [
            'document_type', 'customer', 'location', 'paid_amount', 
            'date', 'due_date', 'currency', 'notes', 'terms', 'items_data'
        ]
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-control', 'id': 'document_type'}),
            'customer': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Search or select customer...'
            }),
            'location': forms.Select(attrs={'class': 'form-control select2'}),
            'paid_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'id': 'id_paid_amount'
            }),
            'date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'currency': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Get models from other apps
        Customer = __import__('transactions.models', fromlist=['Customer']).Customer
        Location = __import__('core.models', fromlist=['Location']).Location
        
        # Set querysets
        self.fields['customer'].queryset = Customer.objects.all()
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = "Select Customer"
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location
        
        # Set initial dates
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now()
            self.fields['due_date'].initial = timezone.now().date() + timezone.timedelta(days=30)

    def clean(self):
        cleaned_data = super().clean()
        document_type = cleaned_data.get('document_type')
        customer = cleaned_data.get('customer')
        paid_amount = cleaned_data.get('paid_amount', 0)
        items_data = cleaned_data.get('items_data', '[]')
        location = cleaned_data.get('location')
        
        # Parse items data
        try:
            items = json.loads(items_data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid items data format")
        
        # Validate at least one item
        if not items or len(items) == 0:
            raise ValidationError("Please add at least one product to the sale")
        
        # Customer is required for invoices
        if document_type == 'invoice' and not customer:
            raise ValidationError("Customer is required for invoices.")
        
        # Calculate total amount from items
        total_amount = sum(float(item.get('total', 0)) for item in items)
        
        # Paid amount cannot exceed total amount
        if paid_amount > total_amount:
            raise ValidationError(f"Paid amount (${paid_amount}) cannot exceed total amount (${total_amount:.2f}).")
        
        # Validate stock availability for each item
        for item in items:
            product_id = item.get('product_id')
            quantity = int(item.get('quantity', 0))
            
            if product_id and location and quantity > 0:
                try:
                    product = Product.objects.get(id=product_id)
                    stock = ProductStock.objects.get(product=product, location=location)
                    if stock.quantity < quantity:
                        raise ValidationError(
                            f"Not enough stock for {product.name}. Available: {stock.quantity}, Requested: {quantity}"
                        )
                except ProductStock.DoesNotExist:
                    raise ValidationError(f"No stock found for {product.name} at {location.name}")
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.created_by = self.user
        
        if commit:
            instance.save()
        
        return instance

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'payment_method', 'reference_number', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'payment_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.sale = kwargs.pop('sale', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.sale:
            # Set max amount to balance due
            max_amount = self.sale.balance_due
            self.fields['amount'].widget.attrs['max'] = max_amount
            self.fields['amount'].help_text = f'Balance due: {max_amount:.2f}'

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.sale and amount > self.sale.balance_due:
            raise ValidationError(
                f"Payment amount cannot exceed balance due of {self.sale.balance_due:.2f}"
            )
        return amount

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.sale:
            instance.sale = self.sale
        if self.user:
            instance.received_by = self.user
        
        if commit:
            instance.save()
        return instance

class PurchaseForm(forms.ModelForm):
    items_data = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'id_items_data'}),
        required=False,
        initial='[]'
    )
    
    class Meta:
        model = __import__('inventory.models', fromlist=['Purchase']).Purchase
        fields = ['supplier_name', 'location', 'purchase_date', 'notes', 'items_data']
        widgets = {
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Select(attrs={'class': 'form-control select2'}),
            'purchase_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location
        
        # Set initial date
        if not self.instance.pk:
            self.fields['purchase_date'].initial = timezone.now()

class TransferForm(forms.ModelForm):
    items_data = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'id_items_data'}),
        required=False,
        initial='[]'
    )
    
    class Meta:
        model = __import__('inventory.models', fromlist=['TransferBatch']).TransferBatch
        fields = ['from_location', 'to_location', 'transfer_date', 'notes', 'items_data']
        widgets = {
            'from_location': forms.Select(attrs={'class': 'form-control select2'}),
            'to_location': forms.Select(attrs={'class': 'form-control select2'}),
            'transfer_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['from_location'].queryset = self.locations
            self.fields['to_location'].queryset = self.locations
        
        # Set initial from_location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['from_location'].initial = self.user.profile.assigned_location
        
        # Set initial date
        if not self.instance.pk:
            self.fields['transfer_date'].initial = timezone.now()

    def clean(self):
        cleaned_data = super().clean()
        from_location = cleaned_data.get('from_location')
        to_location = cleaned_data.get('to_location')
        
        if from_location and to_location and from_location == to_location:
            raise ValidationError("Source and destination locations cannot be the same.")
        
        return cleaned_data

class PurchaseOrderForm(forms.ModelForm):
    items_data = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'id_items_data'}),
        required=False,
        initial='[]'
    )
    
    class Meta:
        model = __import__('inventory.models', fromlist=['PurchaseOrder']).PurchaseOrder
        fields = ['supplier_name', 'location', 'order_date', 'expected_date', 'notes', 'items_data']
        widgets = {
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Select(attrs={'class': 'form-control select2'}),
            'order_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'expected_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location
        
        # Set initial dates
        if not self.instance.pk:
            self.fields['order_date'].initial = timezone.now()
            self.fields['expected_date'].initial = timezone.now().date() + timezone.timedelta(days=7)

class SaleOrderForm(forms.ModelForm):
    items_data = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'id_items_data'}),
        required=False,
        initial='[]'
    )
    
    class Meta:
        model = __import__('inventory.models', fromlist=['SaleOrder']).SaleOrder
        fields = ['customer', 'location', 'sale_date', 'notes', 'items_data']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-control select2'}),
            'location': forms.Select(attrs={'class': 'form-control select2'}),
            'sale_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.locations = kwargs.pop('locations', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Get customer model
        Customer = __import__('transactions.models', fromlist=['Customer']).Customer
        
        # Set querysets
        self.fields['customer'].queryset = Customer.objects.all()
        
        # Limit locations to user's accessible locations
        if self.locations is not None:
            self.fields['location'].queryset = self.locations
        
        # Set initial location for non-admin users
        if self.user and not self.user.profile.can_access_all_locations and self.user.profile.assigned_location:
            self.fields['location'].initial = self.user.profile.assigned_location
        
        # Set initial date
        if not self.instance.pk:
            self.fields['sale_date'].initial = timezone.now()

from .models import CompanyDetails

class CompanyDetailsForm(forms.ModelForm):
    class Meta:
        model = CompanyDetails
        fields = [
            'name', 'address', 'phone', 'email', 'website', 'tax_id',
            'bank_name', 'bank_account', 'bank_branch', 'logo',
            'invoice_prefix', 'quotation_prefix', 'receipt_prefix',
            'invoice_footer', 'quotation_footer'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'quotation_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'receipt_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'quotation_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }   


from django import forms
from .models import Payment

class SalePaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method', 'payment_date', 'notes']  # Remove 'reference'
        widgets = {
            'payment_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control',
                'id': 'payment_date'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter amount',
                'step': '0.01',
                'min': '0.01',
                'id': 'amount'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-control',
                'id': 'payment_method'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Payment details',
                'id': 'notes'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial date to today
        from django.utils import timezone
        self.fields['payment_date'].initial = timezone.now().date()
