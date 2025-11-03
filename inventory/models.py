from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User
from core.models import Location
from transactions.models import Customer
from django.utils import timezone

# Define choices at the top of the file - REMOVE DUPLICATES
class DocumentType(models.TextChoices):
    INVOICE = 'invoice', 'Invoice'
    QUOTATION = 'quotation', 'Quotation'
    RECEIPT = 'receipt', 'Receipt'
    DELIVERY_NOTE = 'delivery_note', 'Delivery Note'
    CREDIT_NOTE = 'credit_note', 'Credit Note'

class Currency(models.TextChoices):
    USD = 'USD', 'US Dollar'
    EUR = 'EUR', 'Euro'
    GBP = 'GBP', 'British Pound'
    KES = 'KES', 'Kenyan Shilling'
    TZS = 'TZS', 'Tanzanian Shilling'
    UGX = 'UGX', 'Ugandan Shilling'
    ZAR = 'ZAR', 'South African Rand'
    XAF = 'XAF', 'Central African CFA Franc'
    XOF = 'XOF', 'West African CFA Franc'
    GHS = 'GHS', 'Ghanaian Cedi'
    NGN = 'NGN', 'Nigerian Naira'

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, unique=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_level = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def total_stock(self):
        return sum(stock.quantity for stock in self.stocks.all())

class ProductStock(models.Model):
    product = models.ForeignKey(Product, related_name='stocks', on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('product', 'location')

    def __str__(self):
        return f"{self.product.name} @ {self.location.name}"

class Purchase(models.Model):
    """Main purchase that can contain multiple products"""
    reference = models.CharField(max_length=20, unique=True, blank=True)
    supplier_name = models.CharField(max_length=200)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchase_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"PUR-{self.reference} - {self.supplier_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PUR-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)

    def get_total_quantity(self):
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0

    def get_items_count(self):
        return self.items.count()

class PurchaseItem(models.Model):
    """Individual items within a purchase"""
    purchase = models.ForeignKey(Purchase, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def get_total_cost(self):
        return self.quantity * self.unit_price
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update stock when purchase item is saved
        if self.purchase.location:
            stock, created = ProductStock.objects.get_or_create(
                product=self.product,
                location=self.purchase.location,
                defaults={'quantity': 0}
            )
            stock.quantity += self.quantity
            stock.save()
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} units"

class TransferBatch(models.Model):
    """Represents a group of stock transfers (like one transfer receipt)."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled')
    ]
    
    reference = models.CharField(max_length=20, unique=True)
    from_location = models.ForeignKey(
        Location, 
        related_name='batch_transfers_out',
        on_delete=models.SET_NULL, 
        null=True
    )
    to_location = models.ForeignKey(
        Location, 
        related_name='batch_transfers_in',
        on_delete=models.SET_NULL, 
        null=True
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(
        User, 
        related_name='batch_confirmed', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    transfer_date = models.DateTimeField(default=timezone.now)

    def get_total_quantity(self):
        """Get total quantity of all items in this batch"""
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0
    
    def get_items_count(self):
        """Get number of items in this batch"""
        return self.items.count()

    def __str__(self):
        return f"Batch {self.reference} - {self.status}"

    def confirm(self, user):
        """Confirm all transfers in this batch"""
        if self.status != 'pending':
            raise ValueError("Only pending batches can be confirmed.")
        
        for transfer in self.items.all():
            transfer.confirm_transfer(user)

        self.status = 'confirmed'
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.save()

    def cancel(self):
        """Cancel the entire batch"""
        if self.status != 'pending':
            raise ValueError("Only pending batches can be cancelled.")
        
        self.status = 'cancelled'
        self.save()

class StockTransfer(models.Model):
    """Each individual product transfer, linked to a batch."""
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (CONFIRMED, 'Confirmed'),
        (CANCELLED, 'Cancelled'),
    ]

    batch = models.ForeignKey(
        TransferBatch, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    transfer_date = models.DateTimeField(default=timezone.now)
    transferred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-transfer_date']

    def __str__(self):
        return f"{self.product.name} ({self.quantity}) - {self.status}"

    def confirm_transfer(self, confirmed_by_user):
        """Confirm the transfer and update stock"""
        if self.status != self.PENDING:
            raise ValueError("Only pending transfers can be confirmed")
        
        if not self.batch.from_location or not self.batch.to_location:
            raise ValueError("Batch locations are not set")
        
        from_location = self.batch.from_location
        to_location = self.batch.to_location

        # Check stock at source
        try:
            from_stock = ProductStock.objects.get(product=self.product, location=from_location)
            if from_stock.quantity < self.quantity:
                raise ValueError(f"Not enough stock at {from_location.name}. Available: {from_stock.quantity}, Requested: {self.quantity}")
        except ProductStock.DoesNotExist:
            raise ValueError(f"No stock found for {self.product.name} at {from_location.name}")

        # Deduct from source and add to destination
        from_stock.quantity -= self.quantity
        from_stock.save()

        to_stock, _ = ProductStock.objects.get_or_create(
            product=self.product,
            location=to_location,
            defaults={'quantity': 0}
        )
        to_stock.quantity += self.quantity
        to_stock.save()

        # Mark as confirmed
        self.status = self.CONFIRMED
        self.save()

    def cancel_transfer(self):
        """Cancel this individual transfer"""
        if self.status != self.PENDING:
            raise ValueError("Only pending transfers can be cancelled")
        
        self.status = self.CANCELLED
        self.save()

class RetailStock(models.Model):
    """Tracks retail stock separate from main inventory."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('product', 'location')

    def __str__(self):
        return f"{self.product.name} @ {self.location.name} (Retail)"

class RetailSale(models.Model):
    """A retail sale where the customer pays any amount and receives corresponding quantity."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    amount_given = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_given = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_date = models.DateTimeField(auto_now_add=True)
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        # Calculate quantity based on amount given
        self.quantity_given = self.amount_given / self.unit_price

        # Convert to integer for ProductStock (since it uses PositiveIntegerField)
        quantity_int = int(self.quantity_given)
        
        # Deduct from main ProductStock
        main_stock = ProductStock.objects.get(product=self.product, location=self.location)
        if main_stock.quantity < quantity_int:
            raise ValueError(f"Not enough stock in main inventory. Available: {main_stock.quantity}")
        
        main_stock.quantity -= quantity_int
        main_stock.save()

        # Add to RetailStock (this uses DecimalField so no conversion needed)
        retail_stock, _ = RetailStock.objects.get_or_create(product=self.product, location=self.location)
        retail_stock.quantity += self.quantity_given
        retail_stock.save()

        super().save(*args, **kwargs)

class Sale(models.Model):
    DOCUMENT_STATUS = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    customer = models.ForeignKey('transactions.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    location = models.ForeignKey('core.Location', on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Document fields
    document_type = models.CharField(
        max_length=20, 
        choices=DocumentType.choices, 
        default=DocumentType.INVOICE
    )
    document_number = models.CharField(max_length=50, unique=True, blank=True)
    document_status = models.CharField(
        max_length=20, 
        choices=DOCUMENT_STATUS, 
        default='draft'
    )
    currency = models.CharField(
        max_length=3, 
        choices=Currency.choices, 
        default=Currency.UGX
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    
    # Track creation and updates
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='sales_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        # Generate document number if not set
        if not self.document_number:
            prefix = self.document_type.upper()[:3]
            last_doc = Sale.objects.filter(document_type=self.document_type).order_by('-id').first()
            next_number = 1 if not last_doc else int(last_doc.document_number.split('-')[-1]) + 1
            self.document_number = f"{prefix}-{timezone.now().year}-{next_number:06d}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        customer_name = self.customer.name if self.customer else 'Walk-in'
        return f"{self.document_number} - {customer_name} - ${self.total_amount}"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self):
        if self.due_date and self.balance_due > 0:
            return timezone.now().date() > self.due_date
        return False

    @property
    def payment_status(self):
        """Calculate payment status based on paid amount"""
        if self.paid_amount >= self.total_amount:
            return 'fully_paid'
        elif self.paid_amount > 0:
            return 'partially_paid'
        else:
            return 'not_paid'
    
    @property 
    def is_fully_paid(self):
        """Check if sale is fully paid"""
        return self.balance_due <= 0


    def update_payment_status(self):
        """Update document status based on payment"""
        if self.paid_amount >= self.total_amount:
            self.document_status = 'paid'
        elif self.paid_amount > 0 and self.document_status == 'draft':
            self.document_status = 'sent'
        self.save()

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        # Calculate total price
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        
        # Update sale total (but don't handle stock here anymore)
        if self.sale.pk:
            self.sale.total_amount = sum(item.total_price for item in self.sale.items.all())
            self.sale.save()

    def __str__(self):
        return f"{self.product.name} - {self.quantity} x ${self.unit_price}"

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('mobile_money', 'Mobile Money'),
        ('check', 'Check'),
        ('other', 'Other'),
    ]
    
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateTimeField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment of {self.amount} for {self.sale.document_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update sale's paid amount
        self.sale.paid_amount = sum(payment.amount for payment in self.sale.payments.all())
        
        # Update sale status based on payment
        if self.sale.paid_amount >= self.sale.total_amount:
            self.sale.document_status = 'paid'
        elif self.sale.paid_amount > 0:
            self.sale.document_status = 'sent'
        elif self.sale.document_status == 'paid' and self.sale.paid_amount < self.sale.total_amount:
            self.sale.document_status = 'sent'
        
        self.sale.save()

class PurchaseOrder(models.Model):
    """Main purchase order that can contain multiple products"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    reference = models.CharField(max_length=20, unique=True)
    supplier_name = models.CharField(max_length=200)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateTimeField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PO-{self.reference} - {self.supplier_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PO-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)

    def get_total_quantity(self):
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0

    def get_items_count(self):
        return self.items.count()

    def mark_received(self):
        """Mark purchase order as received and update stock"""
        if self.status != 'ordered':
            raise ValueError("Only ordered purchases can be marked as received")
        
        for item in self.items.all():
            if self.location:
                stock, created = ProductStock.objects.get_or_create(
                    product=item.product,
                    location=self.location,
                    defaults={'quantity': 0}
                )
                stock.quantity += item.quantity
                stock.save()
        
        self.status = 'received'
        self.save()

class PurchaseOrderItem(models.Model):
    """Individual items within a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def get_total_cost(self):
        return self.quantity * self.unit_price
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} units @ ${self.unit_price}"

class SaleOrder(models.Model):
    """Main sale order that can contain multiple products"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    reference = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey('transactions.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sale_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        customer_name = self.customer.name if self.customer else 'Walk-in'
        return f"SO-{self.reference} - {customer_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SO-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)

    def get_total_quantity(self):
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0

    def get_items_count(self):
        return self.items.count()

    def confirm_order(self):
        """Confirm sale order and update stock"""
        if self.status != 'draft':
            raise ValueError("Only draft sales can be confirmed")
        
        # Check stock availability first
        for item in self.items.all():
            if self.location:
                try:
                    stock = ProductStock.objects.get(
                        product=item.product,
                        location=self.location
                    )
                    if stock.quantity < item.quantity:
                        raise ValueError(f"Not enough stock for {item.product.name}. Available: {stock.quantity}, Requested: {item.quantity}")
                except ProductStock.DoesNotExist:
                    raise ValueError(f"No stock found for {item.product.name} at {self.location.name}")
        
        # Deduct stock
        for item in self.items.all():
            if self.location:
                stock = ProductStock.objects.get(
                    product=item.product,
                    location=self.location
                )
                stock.quantity -= item.quantity
                stock.save()
        
        self.status = 'confirmed'
        self.save()

class SaleOrderItem(models.Model):
    """Individual items within a sale order"""
    sale_order = models.ForeignKey(SaleOrder, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def get_total_price(self):
        return self.quantity * self.unit_price
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} x ${self.unit_price}"


class CompanyDetails(models.Model):
    name = models.CharField(max_length=200, default="Teba Inventory")
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tax ID/VAT Number")
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_account = models.CharField(max_length=50, blank=True, null=True)
    bank_branch = models.CharField(max_length=100, blank=True, null=True)
    
    # Document settings
    invoice_prefix = models.CharField(max_length=10, default="INV")
    quotation_prefix = models.CharField(max_length=10, default="QUO")
    receipt_prefix = models.CharField(max_length=10, default="REC")
    
    # Footer text for documents
    invoice_footer = models.TextField(blank=True, null=True, help_text="Footer text for invoices")
    quotation_footer = models.TextField(blank=True, null=True, help_text="Footer text for quotations")
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Company Details"
        verbose_name_plural = "Company Details"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one company details record exists
        if not self.pk and CompanyDetails.objects.exists():
            # Update the existing record instead of creating new one
            existing = CompanyDetails.objects.first()
            existing.name = self.name
            existing.address = self.address
            existing.phone = self.phone
            existing.email = self.email
            existing.website = self.website
            existing.logo = self.logo
            existing.tax_id = self.tax_id
            existing.bank_name = self.bank_name
            existing.bank_account = self.bank_account
            existing.bank_branch = self.bank_branch
            existing.invoice_prefix = self.invoice_prefix
            existing.quotation_prefix = self.quotation_prefix
            existing.receipt_prefix = self.receipt_prefix
            existing.invoice_footer = self.invoice_footer
            existing.quotation_footer = self.quotation_footer
            existing.save()
            return
        super().save(*args, **kwargs)


class StockTake(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    reference = models.CharField(max_length=50, unique=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    start_date = models.DateTimeField(auto_now_add=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"StockTake {self.reference} - {self.location.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"ST-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)

    def get_total_items(self):
        return self.items.count()

    def get_counted_items(self):
        return self.items.filter(quantity_counted__isnull=False).count()

    def get_uncounted_items(self):
        return self.items.filter(quantity_counted__isnull=True).count()

    def complete_stocktake(self):
        """Complete the stocktake and update actual stock quantities"""
        if self.status != 'completed':
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()

            # Update actual stock quantities
            for item in self.items.all():
                if item.quantity_counted is not None:
                    # Update the product stock
                    stock, created = ProductStock.objects.get_or_create(
                        product=item.product,
                        location=self.location,
                        defaults={'quantity': item.quantity_counted}
                    )
                    if not created:
                        stock.quantity = item.quantity_counted
                        stock.save()


class StockTakeItem(models.Model):
    stock_take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_on_hand = models.IntegerField(default=0)  # System quantity before stocktake
    quantity_counted = models.IntegerField(null=True, blank=True)  # Physical count
    variance = models.IntegerField(default=0)  # difference: counted - on_hand
    notes = models.TextField(blank=True)
    counted_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ['stock_take', 'product']

    def save(self, *args, **kwargs):
        # Calculate variance
        if self.quantity_counted is not None and self.quantity_on_hand is not None:
            self.variance = self.quantity_counted - self.quantity_on_hand
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.quantity_counted}"      
