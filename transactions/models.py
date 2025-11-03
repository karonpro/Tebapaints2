from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import Location
from django.contrib.auth.models import User

User = get_user_model()
class Customer(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    location = models.ForeignKey('core.Location', on_delete=models.SET_NULL, null=True, blank=True)  # Use string reference
    tin = models.CharField(max_length=50, blank=True, null=True)
    supply = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # ADD THIS LINE
    created_at = models.DateTimeField(auto_now_add=True)


    @property
    def display_balance(self):
        """Display balance that combines manual balance and sales balance"""
        sales_balance = self.total_balance
        return sales_balance + self.balance
    # ... keep all your other properties and methods the same ...
    @property
    def total_supply(self):
        return sum(h.amount for h in self.supply_history.all())

    @property
    def total_payment(self):
        return sum(p.amount for p in self.payments.all())

    @property
    def last_payment(self):
        return self.payments.order_by('-date').first()

    @property
    def balance_color(self):
        balance = self.balance
        if balance > 1000:
            return 'green'
        elif 0 < balance <= 1000:
            return 'yellow'
        else:
            return 'red'

    def __str__(self):
        return self.name
    
    def get_sales_queryset(self):
        """Get sales for this customer without circular imports"""
        try:
            from django.apps import apps
            Sale = apps.get_model('inventory', 'Sale')
            return Sale.objects.filter(customer=self)
        except (LookupError, ImportError):
            from django.db.models.query import QuerySet
            return QuerySet().none()
    
    @property
    def balance_due(self):
        """Sum of unpaid balances from all sent sales"""
        try:
            sales = self.get_sales_queryset().filter(document_status='sent')
            return sum(sale.balance_due for sale in sales)
        except Exception as e:
            return 0

    @property
    def total_sales_amount(self):
        """Calculate total sales amount for this customer"""
        try:
            from django.db.models import Sum
            sales = self.get_sales_queryset()
            return sales.aggregate(total=Sum('total_amount'))['total'] or 0
        except Exception as e:
            return 0

    @property
    def total_paid_amount(self):
        """Calculate total paid amount for this customer"""
        try:
            from django.db.models import Sum
            sales = self.get_sales_queryset()
            return sales.aggregate(total=Sum('paid_amount'))['total'] or 0
        except Exception as e:
            return 0

    @property
    def total_balance(self):
        """Calculate total balance from all sales"""
        try:
            return self.total_sales_amount - self.total_paid_amount
        except Exception as e:
            return 0

    @property
    def total_sales_count(self):
        """Count total sales for this customer"""
        try:
            return self.get_sales_queryset().count()
        except Exception as e:
            return 0
    
    @property
    def overdue_balance(self):
        """Calculate total overdue balance for this customer"""
        try:
            overdue_sales = self.get_sales_queryset().filter(
                document_status='sent',
                due_date__lt=timezone.now().date()
            )
            return sum(sale.balance_due for sale in overdue_sales)
        except Exception as e:
            return 0

    @property
    def unpaid_balance(self):
        """Calculate total unpaid balance (all unpaid sales)"""
        try:
            unpaid_sales = self.get_sales_queryset().filter(
                document_status__in=['sent', 'partially_paid']
            )
            return sum(sale.balance_due for sale in unpaid_sales)
        except Exception as e:
            return 0

    @property
    def recent_sales(self):
        """Get recent sales for this customer"""
        try:
            return self.get_sales_queryset().select_related('location').order_by('-date')[:5]
        except Exception as e:
            return []


    
class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('mobile', 'Mobile Money')
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    notes = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True)  # Add this field
    date = models.DateField(default=timezone.now)

    # Remove the save method that updates customer.balance
    # The balance will be calculated dynamically from sales

    def __str__(self):
        return f"{self.customer.name} - {self.amount} - {self.date}"
class Expense(models.Model):
    name = models.CharField(max_length=255)  # Name of the expense
    notes = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(auto_now_add=False)  # or just omit auto_now_add
 
    def __str__(self):
        return self.name


class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transactions')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wholesale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    debt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    accounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_sales(self):
        return (self.paid or 0) + (self.customer_balance or 0) + (self.wholesale or 0)

    @property
    def total_cashout(self):
        return (self.debt or 0) + (self.cash or 0) + (self.accounts or 0) + (self.expenses or 0)

    @property
    def difference(self):
        return self.total_sales - self.total_cashout

    @property
    def less_excess(self):
        return self.difference - (self.opening_balance or 0)

from django.db import models

class ExpenseName(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class SupplyHistory(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='supply_history')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # Only update customer supply/balance when a new record is added
            self.customer.supply += self.amount
            self.customer.balance += self.amount
            self.customer.save()

from django.db import models
from django.utils import timezone

class BalanceAdjustment(models.Model):
    ADJUSTMENT_TYPES = [
        ('credit', 'Add Credit'),
        ('debit', 'Deduct Balance'),
        ('supply', 'Supply Addition'),
        ('payment', 'Manual Payment'),
    ]
    
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='balance_adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.adjustment_type} - ${self.amount}"
    
from django.db import models
from django.contrib.auth.models import User

class DebtTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('supply', 'Goods Supply'),
        ('payment', 'Payment Received'),
    )
    
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    notes = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.name} - {self.transaction_type} - {self.amount}"
    