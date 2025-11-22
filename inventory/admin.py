# inventory/admin.py
from django.contrib import admin
from django.db.models import Count, Sum
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Category, Product, ProductStock, Purchase, PurchaseItem,
    Sale, SaleItem, StockTransfer, TransferBatch,
    Supplier, RetailStock, RetailSale, Payment,
    PurchaseOrder, PurchaseOrderItem, SaleOrder, SaleOrderItem
)

# ==================== CATEGORY ADMIN ====================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'product_count']
    search_fields = ['name', 'description']
    list_per_page = 20
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'

# ==================== PRODUCT ADMIN ====================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'cost_price', 'selling_price', 'reorder_level', 'total_stock_display']
    list_filter = ['category', 'created_at']
    search_fields = ['name', 'sku', 'category__name']
    readonly_fields = ['created_at', 'total_stock_display']
    list_per_page = 20
    
    def total_stock_display(self, obj):
        return obj.total_stock
    total_stock_display.short_description = 'Total Stock'

# ==================== PRODUCT STOCK ADMIN ====================
@admin.register(ProductStock)
class ProductStockAdmin(admin.ModelAdmin):
    list_display = ['product', 'location', 'quantity', 'stock_status']
    list_filter = ['location', 'product__category']
    search_fields = ['product__name', 'location__name']
    list_per_page = 20
    
    def stock_status(self, obj):
        if obj.quantity == 0:
            return format_html('<span style="color: red;">● Out of Stock</span>')
        elif obj.quantity <= obj.product.reorder_level:
            return format_html('<span style="color: orange;">● Low Stock</span>')
        else:
            return format_html('<span style="color: green;">● In Stock</span>')
    stock_status.short_description = 'Status'

# ==================== PURCHASE ITEM INLINE ====================
class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    fields = ['product', 'quantity', 'unit_price', 'total_cost_display']
    readonly_fields = ['total_cost_display']
    autocomplete_fields = ['product']
    
    def total_cost_display(self, obj):
        if obj.pk:
            return f"${obj.get_total_cost():.2f}"
        return "-"
    total_cost_display.short_description = 'Total Cost'

# ==================== PURCHASE ADMIN ====================
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'supplier_name', 'location', 'items_count', 
        'total_quantity', 'total_amount', 'purchase_date', 'created_by'
    ]
    list_filter = ['supplier_name', 'location', 'purchase_date']
    search_fields = ['reference', 'supplier_name', 'notes', 'items__product__name']
    readonly_fields = ['reference', 'total_amount', 'created_by', 'purchase_date_display']
    inlines = [PurchaseItemInline]
    date_hierarchy = 'purchase_date'
    list_per_page = 20
    
    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = 'Items'
    
    def total_quantity(self, obj):
        return obj.get_total_quantity()
    total_quantity.short_description = 'Total Qty'
    
    def purchase_date_display(self, obj):
        return obj.purchase_date
    purchase_date_display.short_description = 'Purchase Date'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# ==================== PURCHASE ITEM ADMIN ====================
@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ['purchase_reference', 'product', 'quantity', 'unit_price', 'total_cost']
    list_filter = ['purchase__supplier_name', 'product__category']
    search_fields = ['product__name', 'purchase__reference']
    list_per_page = 20
    
    def purchase_reference(self, obj):
        return obj.purchase.reference
    purchase_reference.short_description = 'Purchase Reference'
    purchase_reference.admin_order_field = 'purchase__reference'
    
    def total_cost(self, obj):
        return f"${obj.get_total_cost():.2f}"
    total_cost.short_description = 'Total Cost'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('purchase', 'product')

# ==================== SALE ITEM INLINE ====================
class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    fields = ['product', 'quantity', 'unit_price', 'total_price']
    readonly_fields = ['total_price']
    autocomplete_fields = ['product']

# ==================== SALE ADMIN ====================
@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'document_type', 'customer_display', 'location', 
        'items_count', 'total_amount', 'paid_amount', 'balance_due_display', 
        'document_status', 'date'
    ]
    list_filter = ['document_type', 'document_status', 'location', 'date', 'currency']
    search_fields = ['document_number', 'customer__name', 'items__product__name']
    readonly_fields = ['document_number', 'total_amount', 'created_at', 'updated_at', 'balance_due_display']
    inlines = [SaleItemInline]
    date_hierarchy = 'date'
    list_per_page = 20
    
    fieldsets = (
        ('Document Information', {
            'fields': ('document_type', 'document_number', 'document_status', 'currency')
        }),
        ('Parties & Location', {
            'fields': ('customer', 'location')
        }),
        ('Dates', {
            'fields': ('date', 'due_date')
        }),
        ('Financials', {
            'fields': ('total_amount', 'paid_amount', 'balance_due_display')
        }),
        ('Additional Information', {
            'fields': ('notes', 'terms')
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def customer_display(self, obj):
        return obj.customer.name if obj.customer else 'Walk-in'
    customer_display.short_description = 'Customer'
    customer_display.admin_order_field = 'customer__name'

    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = 'Items'

    def balance_due_display(self, obj):
        return f"${obj.balance_due:.2f}"
    balance_due_display.short_description = 'Balance Due'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# ==================== SALE ITEM ADMIN ====================
@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ['sale_document', 'product', 'quantity', 'unit_price', 'total_price']
    list_filter = ['sale__document_type', 'sale__location', 'product__category']
    search_fields = ['sale__document_number', 'product__name']
    readonly_fields = ['total_price']
    list_per_page = 20
    
    def sale_document(self, obj):
        return obj.sale.document_number
    sale_document.short_description = 'Sale Document'
    sale_document.admin_order_field = 'sale__document_number'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sale', 'product')

# ==================== STOCK TRANSFER INLINE ====================
class StockTransferInline(admin.TabularInline):
    model = StockTransfer
    extra = 1
    fields = ['product', 'quantity', 'status', 'transfer_date']
    readonly_fields = ['status', 'transfer_date']
    autocomplete_fields = ['product']

# ==================== TRANSFER BATCH ADMIN ====================
@admin.register(TransferBatch)
class TransferBatchAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'from_location', 'to_location', 'status', 
        'items_count', 'total_quantity', 'created_by', 'created_at'
    ]
    list_filter = ['status', 'from_location', 'to_location', 'created_at']
    search_fields = ['reference', 'from_location__name', 'to_location__name', 'notes']
    readonly_fields = ['reference', 'created_by', 'confirmed_by', 'confirmed_at', 'created_at']
    inlines = [StockTransferInline]
    date_hierarchy = 'created_at'
    list_per_page = 20
    actions = ['confirm_batches', 'cancel_batches']
    
    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = 'Items'
    
    def total_quantity(self, obj):
        return obj.get_total_quantity()
    total_quantity.short_description = 'Total Qty'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')
    
    def confirm_batches(self, request, queryset):
        successful = 0
        failed = 0
        
        for batch in queryset.filter(status='pending'):
            try:
                batch.confirm(request.user)
                successful += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error confirming batch {batch.reference}: {str(e)}", 
                    level='error'
                )
                failed += 1
        
        if successful:
            self.message_user(
                request, 
                f"Successfully confirmed {successful} batch(es)."
            )
        if failed:
            self.message_user(
                request,
                f"Failed to confirm {failed} batch(es).",
                level='warning'
            )
    
    confirm_batches.short_description = "Confirm selected transfer batches"

    def cancel_batches(self, request, queryset):
        for batch in queryset.filter(status='pending'):
            try:
                batch.cancel()
            except Exception as e:
                self.message_user(
                    request,
                    f"Error cancelling batch {batch.reference}: {str(e)}",
                    level='error'
                )
        
        self.message_user(
            request,
            f"Cancelled {queryset.filter(status='pending').count()} batch(es)."
        )
    
    cancel_batches.short_description = "Cancel selected transfer batches"
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# ==================== STOCK TRANSFER ADMIN ====================
@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'product', 'from_location', 'to_location', 
        'quantity', 'status', 'batch_reference', 'transfer_date'
    ]
    list_filter = ['status', 'batch__from_location', 'batch__to_location', 'transfer_date']
    search_fields = ['product__name', 'product__sku', 'batch__reference']
    readonly_fields = ['transfer_date', 'transferred_by']
    list_per_page = 20
    actions = ['confirm_transfers', 'cancel_transfers']

    def from_location(self, obj):
        return obj.batch.from_location.name if obj.batch and obj.batch.from_location else "-"
    from_location.short_description = "From Location"
    from_location.admin_order_field = 'batch__from_location'

    def to_location(self, obj):
        return obj.batch.to_location.name if obj.batch and obj.batch.to_location else "-"
    to_location.short_description = "To Location"
    to_location.admin_order_field = 'batch__to_location'

    def batch_reference(self, obj):
        return obj.batch.reference if obj.batch else "-"
    batch_reference.short_description = "Batch Reference"
    batch_reference.admin_order_field = 'batch__reference'

    def confirm_transfers(self, request, queryset):
        successful = 0
        failed = 0
        
        for transfer in queryset.filter(status=StockTransfer.PENDING):
            try:
                transfer.confirm_transfer(request.user)
                successful += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error confirming transfer {transfer}: {str(e)}", 
                    level='error'
                )
                failed += 1
        
        if successful:
            self.message_user(
                request, 
                f"Successfully confirmed {successful} transfer(s)."
            )
        if failed:
            self.message_user(
                request,
                f"Failed to confirm {failed} transfer(s).",
                level='warning'
            )
    
    confirm_transfers.short_description = "Confirm selected transfers"

    def cancel_transfers(self, request, queryset):
        for transfer in queryset.filter(status=StockTransfer.PENDING):
            try:
                transfer.cancel_transfer()
            except Exception as e:
                self.message_user(
                    request,
                    f"Error cancelling transfer {transfer}: {str(e)}",
                    level='error'
                )
        
        self.message_user(
            request,
            f"Cancelled {queryset.filter(status=StockTransfer.PENDING).count()} transfer(s)."
        )
    
    cancel_transfers.short_description = "Cancel selected transfers"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'batch', 'batch__from_location', 'batch__to_location'
        )

# ==================== SUPPLIER ADMIN ====================
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email', 'phone', 'address_preview']
    search_fields = ['name', 'contact_person', 'email', 'phone']
    list_per_page = 20
    
    def address_preview(self, obj):
        if obj.address:
            return obj.address[:50] + '...' if len(obj.address) > 50 else obj.address
        return "-"
    address_preview.short_description = 'Address'

# ==================== RETAIL STOCK ADMIN ====================
@admin.register(RetailStock)
class RetailStockAdmin(admin.ModelAdmin):
    list_display = ['product', 'location', 'quantity']
    list_filter = ['location', 'product__category']
    search_fields = ['product__name']
    list_per_page = 20

# ==================== RETAIL SALE ADMIN ====================
@admin.register(RetailSale)
class RetailSaleAdmin(admin.ModelAdmin):
    list_display = ['product', 'location', 'amount_given', 'quantity_given', 'unit_price', 'sale_date', 'sold_by']
    list_filter = ['location', 'sale_date']
    search_fields = ['product__name']
    readonly_fields = ['quantity_given']
    list_per_page = 20

# ==================== PAYMENT ADMIN ====================
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['sale_document', 'amount', 'payment_method', 'payment_date', 'received_by']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['sale__document_number', 'reference_number']
    readonly_fields = ['created_at']
    list_per_page = 20
    
    def sale_document(self, obj):
        return obj.sale.document_number
    sale_document.short_description = 'Sale Document'
    sale_document.admin_order_field = 'sale__document_number'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sale', 'received_by')

# ==================== PURCHASE ORDER ITEM INLINE ====================
class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ['product', 'quantity', 'unit_price', 'total_cost_display']
    readonly_fields = ['total_cost_display']
    autocomplete_fields = ['product']
    
    def total_cost_display(self, obj):
        if obj.pk:
            return f"${obj.get_total_cost():.2f}"
        return "-"
    total_cost_display.short_description = 'Total Cost'

# ==================== PURCHASE ORDER ADMIN ====================
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'supplier_name', 'location', 'status', 
        'items_count', 'total_amount', 'order_date', 'created_by'
    ]
    list_filter = ['status', 'supplier_name', 'location', 'order_date']
    search_fields = ['reference', 'supplier_name', 'notes']
    readonly_fields = ['reference', 'total_amount', 'created_by', 'created_at', 'updated_at']
    inlines = [PurchaseOrderItemInline]
    date_hierarchy = 'order_date'
    list_per_page = 20
    actions = ['mark_as_ordered', 'mark_as_received', 'mark_as_cancelled']
    
    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = 'Items'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')
    
    def mark_as_ordered(self, request, queryset):
        updated = queryset.update(status='ordered')
        self.message_user(request, f"{updated} purchase order(s) marked as ordered.")
    mark_as_ordered.short_description = "Mark selected as ordered"
    
    def mark_as_received(self, request, queryset):
        for order in queryset.filter(status='ordered'):
            try:
                order.mark_received()
            except Exception as e:
                self.message_user(request, f"Error receiving {order.reference}: {str(e)}", level='error')
        self.message_user(request, f"Processed {queryset.filter(status='ordered').count()} order(s).")
    mark_as_received.short_description = "Mark selected as received"
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f"{updated} purchase order(s) cancelled.")
    mark_as_cancelled.short_description = "Cancel selected orders"
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# ==================== SALE ORDER ITEM INLINE ====================
class SaleOrderItemInline(admin.TabularInline):
    model = SaleOrderItem
    extra = 1
    fields = ['product', 'quantity', 'unit_price', 'total_price_display']
    readonly_fields = ['total_price_display']
    autocomplete_fields = ['product']
    
    def total_price_display(self, obj):
        if obj.pk:
            return f"${obj.get_total_price():.2f}"
        return "-"
    total_price_display.short_description = 'Total Price'

# ==================== SALE ORDER ADMIN ====================
@admin.register(SaleOrder)
class SaleOrderAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'customer_display', 'location', 'status', 
        'items_count', 'total_amount', 'sale_date', 'created_by'
    ]
    list_filter = ['status', 'location', 'sale_date']
    search_fields = ['reference', 'customer__name', 'notes']
    readonly_fields = ['reference', 'total_amount', 'created_by', 'created_at', 'updated_at']
    inlines = [SaleOrderItemInline]
    date_hierarchy = 'sale_date'
    list_per_page = 20
    actions = ['confirm_orders', 'mark_as_delivered', 'cancel_orders']
    
    def customer_display(self, obj):
        return obj.customer.name if obj.customer else 'Walk-in'
    customer_display.short_description = 'Customer'
    
    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = 'Items'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')
    
    def confirm_orders(self, request, queryset):
        for order in queryset.filter(status='draft'):
            try:
                order.confirm_order()
            except Exception as e:
                self.message_user(request, f"Error confirming {order.reference}: {str(e)}", level='error')
        self.message_user(request, f"Processed {queryset.filter(status='draft').count()} order(s).")
    confirm_orders.short_description = "Confirm selected orders"
    
    def mark_as_delivered(self, request, queryset):
        updated = queryset.filter(status='confirmed').update(status='delivered')
        self.message_user(request, f"{updated} sale order(s) marked as delivered.")
    mark_as_delivered.short_description = "Mark selected as delivered"
    
    def cancel_orders(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f"{updated} sale order(s) cancelled.")
    cancel_orders.short_description = "Cancel selected orders"
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# ==================== ADMIN SITE CONFIGURATION ====================
admin.site.site_header = "Inventory Management System"
admin.site.site_title = "Inventory Admin"
admin.site.index_title = "Inventory Administration"