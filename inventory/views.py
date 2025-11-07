# inventory/views.py - COMPLETE VERSION WITH ALL VIEWS
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import StockTake, StockTakeItem  # For stocktake functionality
from django.core.paginator import Paginator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import Sum, Q, F
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.core.exceptions import ValidationError
import uuid
import csv
import json
from django.db.models import (
    Sum, Count, Avg, Min, Max, F, Q, Value, When, Case, 
    IntegerField, DecimalField, FloatField, ExpressionWrapper
)

from .models import (
    Category, Product, ProductStock, Purchase, PurchaseItem, Supplier,
    Sale, SaleItem, StockTransfer, TransferBatch, RetailStock, 
    RetailSale, Currency, Payment, PurchaseOrder, PurchaseOrderItem, 
    SaleOrder, SaleOrderItem, DocumentType, CompanyDetails, StockTake, StockTakeItem 
)
from transactions.models import Customer
from core.models import Location
from .forms import SaleForm, PaymentForm

# Import location utilities
from core.utils import get_user_locations, filter_queryset_by_user_locations, can_user_access_location, get_user_default_location


# =======================
# DASHBOARD
# =======================
@login_required
def inventory_dashboard(request):
    """Inventory Dashboard"""
    try:
        # Get total products count
        total_products = Product.objects.count()
        
        # Get total sales amount (filtered by user locations)
        sales = Sale.objects.all()
        sales = filter_queryset_by_user_locations(sales, request.user)
        total_sales_amount = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Get total purchases amount (filtered by user locations)
        purchases = Purchase.objects.all()
        purchases = filter_queryset_by_user_locations(purchases, request.user)
        total_purchases_amount = purchases.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Get total quantity sold (from SaleItem model)
        sale_items = SaleItem.objects.filter(sale__in=sales)
        total_quantity_sold = sale_items.aggregate(total=Sum('quantity'))['total'] or 0
        
        # Get low stock products (filtered by user locations)
        low_stock_products = Product.objects.filter(
            stocks__quantity__lt=10,
            stocks__location__in=get_user_locations(request.user)
        ).distinct()[:5]
        
        # Get recent sales (filtered by user locations)
        recent_sales = sales.select_related('customer', 'location').order_by('-date')[:5]
        
        # Get recent purchases (filtered by user locations)
        recent_purchases = purchases.select_related('location').order_by('-purchase_date')[:5]
        
        context = {
            'total_products': total_products,
            'total_sales_amount': total_sales_amount,
            'total_purchases_amount': total_purchases_amount,
            'total_quantity_sold': total_quantity_sold,
            'low_stock_products': low_stock_products,
            'recent_sales': recent_sales,
            'recent_purchases': recent_purchases,
        }
        return render(request, 'inventory/dashboard.html', context)
        
    except Exception as e:
        # Fallback if there are any issues
        context = {
            'total_products': 0,
            'total_sales_amount': 0,
            'total_purchases_amount': 0,
            'total_quantity_sold': 0,
            'low_stock_products': [],
            'recent_sales': [],
            'recent_purchases': [],
        }
        return render(request, 'inventory/dashboard.html', context)


# =======================
# PRODUCTS
# =======================
@login_required
def product_list(request):
    # Get user locations
    user_locations = get_user_locations(request.user)
    
    # Base queryset with optimizations
    products = Product.objects.filter(
        stocks__location__in=user_locations
    ).select_related('category').prefetch_related(
        models.Prefetch(
            'stocks',
            queryset=ProductStock.objects.filter(location__in=user_locations).select_related('location')
        )
    ).distinct()
    
    # Handle search
    search_query = request.GET.get('q', '')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
    
    # Handle category filter
    category_filter = request.GET.get('category', '')
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    # Handle sorting
    sort_by = request.GET.get('sort', 'name')
    if sort_by in ['name', 'sku', 'category__name']:
        products = products.order_by(sort_by)
    else:
        products = products.order_by('name')
    
    # Pagination
    paginator = Paginator(products, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Prepare product data
    product_data = []
    low_stock_count = 0
    out_of_stock_count = 0
    
    for product in page_obj:
        stocks = product.stocks.all()  # Already prefetched
        total_stock = sum(stock.quantity for stock in stocks)
        
        if total_stock == 0:
            out_of_stock_count += 1
        elif total_stock <= product.reorder_level:
            low_stock_count += 1
        
        product_data.append({
            'product': product,
            'stocks': stocks,
            'total_stock': total_stock
        })
    
    context = {
        'product_data': product_data,
        'categories': Category.objects.all(),
        'search_query': search_query,
        'category_filter': category_filter,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'page_obj': page_obj,
        'sort_by': sort_by,
    }
    return render(request, 'inventory/product_list.html', context)

@login_required
def product_detail(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related('stocks__location', 'category'), 
        id=product_id
    )
    
    # Get stocks for this product in user's locations only
    user_locations = get_user_locations(request.user)
    stocks = ProductStock.objects.filter(
        product=product, 
        location__in=user_locations
    ).select_related('location')
    
    # Get purchases for this product through PurchaseItem (filtered by user locations)
    purchase_items = PurchaseItem.objects.filter(
        product=product,
        purchase__location__in=user_locations
    ).select_related('purchase', 'purchase__location').order_by('-purchase__purchase_date')
    
    # Get sales for this product through SaleItem (filtered by user locations)
    sale_items = SaleItem.objects.filter(
        product=product,
        sale__location__in=user_locations
    ).select_related('sale', 'sale__customer', 'sale__location').order_by('-sale__date')
    
    # Get transfers (filtered by user locations)
    transfers_out = StockTransfer.objects.filter(
        product=product, 
        batch__from_location__in=user_locations
    ).select_related('batch__from_location', 'batch__to_location', 'transferred_by').order_by('-transfer_date')
    
    transfers_in = StockTransfer.objects.filter(
        product=product, 
        batch__to_location__in=user_locations
    ).select_related('batch__from_location', 'batch__to_location', 'transferred_by').order_by('-transfer_date')

    # Calculate total sold quantity
    total_sold = sum(item.quantity for item in sale_items)
    
    # Calculate total purchased quantity
    total_purchased = sum(item.quantity for item in purchase_items)
    
    # Calculate current stock
    current_stock = sum(stock.quantity for stock in stocks)

    context = {
        'product': product,
        'stocks': stocks,
        'purchase_items': purchase_items,
        'sale_items': sale_items,
        'transfers_out': transfers_out,
        'transfers_in': transfers_in,
        'total_sold': total_sold,
        'total_purchased': total_purchased,
        'current_stock': current_stock,
    }
    return render(request, 'inventory/product_detail.html', context)


@login_required
@transaction.atomic
def product_add(request):
    user_locations = get_user_locations(request.user)
    categories = Category.objects.all()
    
    if request.method == 'POST':
        try:
            # Get form data with proper defaults
            name = request.POST.get('name', '').strip()
            category_id = request.POST.get('category', '')
            cost_price = request.POST.get('cost_price', '0')
            selling_price = request.POST.get('selling_price', '0')
            location_id = request.POST.get('location', '')
            qty = request.POST.get('quantity', '0')
            
            # Validate required fields
            if not name:
                messages.error(request, "Product name is required")
                return redirect('inventory:product_add')
            if not category_id:
                messages.error(request, "Category is required")
                return redirect('inventory:product_add')
            if not location_id:
                messages.error(request, "Location is required")
                return redirect('inventory:product_add')
            
            # Check if user can access the selected location
            try:
                location = Location.objects.get(id=location_id)
                if not can_user_access_location(request.user, location):
                    messages.error(request, "You don't have permission to access this location")
                    return redirect('inventory:product_add')
            except Location.DoesNotExist:
                messages.error(request, "Invalid location selected")
                return redirect('inventory:product_add')
            
            # Convert numeric fields
            try:
                cost_price = float(cost_price)
                selling_price = float(selling_price)
                qty = int(qty)
            except ValueError:
                messages.error(request, "Please enter valid numeric values for prices and quantity")
                return redirect('inventory:product_add')
            
            # Get category
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                messages.error(request, "Invalid category selected")
                return redirect('inventory:product_add')
            
            # Generate unique SKU
            sku = f"SKU-{uuid.uuid4().hex[:8].upper()}"
            
            # Create product
            product = Product(
                name=name,
                category=category,
                sku=sku,
                cost_price=cost_price,
                selling_price=selling_price
            )
            product.save()
            
            # Create product stock
            stock = ProductStock(
                product=product,
                location=location,
                quantity=qty
            )
            stock.save()
            
            messages.success(request, f"Product '{name}' added successfully!")
            return redirect('inventory:product_list')
            
        except Exception as e:
            messages.error(request, f"Error adding product: {str(e)}")
            context = {
                'categories': categories,
                'locations': user_locations,
                'form_data': request.POST
            }
            return render(request, 'inventory/product_add.html', context)
    
    else:
        context = {
            'categories': categories,
            'locations': user_locations,
        }
        return render(request, 'inventory/product_add.html', context)


@login_required
@transaction.atomic
def product_delete(request, pk):
    try:
        product = get_object_or_404(Product, id=pk)
        product_name = product.name
        
        # Delete associated stock records first (only in user's locations)
        user_locations = get_user_locations(request.user)
        ProductStock.objects.filter(product=product, location__in=user_locations).delete()
        
        # Then delete the product
        product.delete()
        
        messages.success(request, f"Product '{product_name}' deleted successfully!")
        return redirect('inventory:product_list')
    
    except Product.DoesNotExist:
        messages.error(request, "Product not found")
        return redirect('inventory:product_list')
    except Exception as e:
        messages.error(request, f"Error deleting product: {str(e)}")
        return redirect('inventory:product_list')


@login_required
@transaction.atomic
def product_edit(request, pk):
    try:
        product = get_object_or_404(Product, id=pk)
        user_locations = get_user_locations(request.user)
        categories = Category.objects.all()
        
        # Get current stock quantities
        current_stocks = {}
        stocks = ProductStock.objects.filter(product=product, location__in=user_locations)
        for stock in stocks:
            current_stocks[stock.location.id] = stock.quantity
        
        if request.method == 'POST':
            try:
                # Get form data
                name = request.POST.get('name', '').strip()
                category_id = request.POST.get('category')
                cost_price = request.POST.get('cost_price', '0')
                selling_price = request.POST.get('selling_price', '0')
                
                # Validate required fields
                if not name:
                    messages.error(request, "Product name is required")
                    return redirect('inventory:product_edit', pk=pk)
                
                if not category_id:
                    messages.error(request, "Category is required")
                    return redirect('inventory:product_edit', pk=pk)
                
                # Get category
                try:
                    category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    messages.error(request, "Invalid category selected")
                    return redirect('inventory:product_edit', pk=pk)
                
                # Convert numeric fields with proper validation
                try:
                    cost_price = float(cost_price) if cost_price else 0.0
                    selling_price = float(selling_price) if selling_price else 0.0
                except (ValueError, TypeError):
                    messages.error(request, "Please enter valid numeric values for prices")
                    return redirect('inventory:product_edit', pk=pk)
                
                # Update product basic info
                product.name = name
                product.category = category
                product.cost_price = cost_price
                product.selling_price = selling_price
                product.save()
                
                # Update stock quantities for each user location
                for location in user_locations:
                    quantity_key = f'quantity_{location.id}'
                    quantity_str = request.POST.get(quantity_key, '')
                    
                    # Handle quantity parsing more carefully
                    try:
                        if quantity_str == '' or quantity_str is None:
                            # If no quantity provided, keep existing quantity or set to 0
                            quantity = current_stocks.get(location.id, 0)
                        else:
                            quantity = int(quantity_str)
                            
                        # Ensure quantity is not negative
                        quantity = max(0, quantity)
                        
                    except (ValueError, TypeError):
                        # If invalid quantity, keep existing quantity
                        quantity = current_stocks.get(location.id, 0)
                        messages.warning(request, f"Invalid quantity for {location.name}, using current value: {quantity}")
                
                    # Update or create ProductStock record
                    stock, created = ProductStock.objects.get_or_create(
                        product=product,
                        location=location,
                        defaults={'quantity': quantity}
                    )
                    
                    if not created:
                        # Only update if quantity actually changed
                        if stock.quantity != quantity:
                            stock.quantity = quantity
                            stock.save()
                
                messages.success(request, f"Product '{name}' updated successfully!")
                return redirect('inventory:product_list')
                
            except Exception as e:
                messages.error(request, f"Error updating product: {str(e)}")
                # Return to form with current data
                context = {
                    'product': product,
                    'categories': categories,
                    'locations': user_locations,
                    'stocks': current_stocks,
                }
                return render(request, 'inventory/product_edit.html', context)
        
        else:
            # GET request - show form with current data
            context = {
                'product': product,
                'categories': categories,
                'locations': user_locations,
                'stocks': current_stocks,
            }
            return render(request, 'inventory/product_edit.html', context)
            
    except Product.DoesNotExist:
        messages.error(request, "Product not found")
        return redirect('inventory:product_list')
    except Exception as e:
        messages.error(request, f"Error loading product: {str(e)}")
        return redirect('inventory:product_list')

# =======================
# PURCHASES
# =======================
@login_required
def purchase_list(request):
    """List all purchases with batch items"""
    # Get purchases filtered by user locations
    purchases = Purchase.objects.all()
    purchases = filter_queryset_by_user_locations(purchases, request.user)
    purchases = purchases.select_related('location', 'created_by').prefetch_related('items__product').order_by('-purchase_date')
    
    # Apply filters
    search_query = request.GET.get('q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    supplier_filter = request.GET.get('supplier', '')
    location_filter = request.GET.get('location', '')
    
    if search_query:
        purchases = purchases.filter(
            Q(supplier_name__icontains=search_query) |
            Q(items__product__name__icontains=search_query) |
            Q(reference__icontains=search_query)
        ).distinct()
    
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    
    if supplier_filter:
        purchases = purchases.filter(supplier_name__icontains=supplier_filter)
    
    if location_filter:
        # Only apply if user has access to this location
        try:
            location = Location.objects.get(id=location_filter)
            if can_user_access_location(request.user, location):
                purchases = purchases.filter(location_id=location_filter)
        except Location.DoesNotExist:
            pass
    
    # Calculate statistics
    total_spent = sum(float(purchase.total_amount) for purchase in purchases)
    total_quantity = sum(purchase.get_total_quantity() for purchase in purchases)
    supplier_names = set(purchase.supplier_name for purchase in purchases if purchase.supplier_name)
    unique_suppliers = len(supplier_names)
    
    # Get user locations for filter dropdown
    locations = get_user_locations(request.user)
    
    # Check if any filters are active
    has_filters = any([search_query, date_from, date_to, supplier_filter, location_filter])
    
    context = {
        'purchases': purchases,
        'locations': locations,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'supplier_filter': supplier_filter,
        'location_filter': location_filter,
        'total_spent': total_spent,
        'total_quantity': total_quantity,
        'unique_suppliers': unique_suppliers,
        'has_filters': has_filters,
    }
    return render(request, 'inventory/purchase_list.html', context)


@login_required
@transaction.atomic
def purchase_add(request):
    """Add new purchase with multiple items"""
    user_locations = get_user_locations(request.user)
    products = Product.objects.all().select_related('category')
    
    # ADD THIS: Get suppliers from database
    suppliers = Supplier.objects.all().order_by('name')
    
    if request.method == "POST":
        # Handle both supplier selection and supplier name input
        supplier_id = request.POST.get('supplier')
        supplier_name = request.POST.get('supplier_name')
        location_id = request.POST.get('location')
        purchase_date = request.POST.get('purchase_date')
        notes = request.POST.get('notes', '')
        items_data = request.POST.get('items_data')

        # Determine supplier name - either from dropdown or text input
        final_supplier_name = ""
        if supplier_id:
            # Get supplier name from database if ID is provided
            try:
                supplier = Supplier.objects.get(id=supplier_id)
                final_supplier_name = supplier.name
            except Supplier.DoesNotExist:
                final_supplier_name = supplier_name or ""
        else:
            final_supplier_name = supplier_name or ""

        if not final_supplier_name.strip():
            messages.error(request, "Supplier name is required")
            return redirect('inventory:purchase_add')
            
        if not location_id:
            messages.error(request, "Location is required")
            return redirect('inventory:purchase_add')

        # Check if user can access the selected location
        try:
            location = Location.objects.get(id=location_id)
            if not can_user_access_location(request.user, location):
                messages.error(request, "You don't have permission to access this location")
                return redirect('inventory:purchase_add')
        except Location.DoesNotExist:
            messages.error(request, "Invalid location selected")
            return redirect('inventory:purchase_add')

        if not items_data:
            messages.error(request, "Please add at least one product")
            return redirect('inventory:purchase_add')

        try:
            items = json.loads(items_data)
            if not items:
                messages.error(request, "Please add at least one product")
                return redirect('inventory:purchase_add')
        except json.JSONDecodeError:
            messages.error(request, "Invalid product data")
            return redirect('inventory:purchase_add')

        # Parse purchase date
        try:
            if purchase_date:
                purchase_datetime = timezone.datetime.fromisoformat(purchase_date)
            else:
                purchase_datetime = timezone.now()
        except (ValueError, TypeError):
            purchase_datetime = timezone.now()

        try:
            # Create Purchase (main purchase record)
            purchase = Purchase.objects.create(
                supplier_name=final_supplier_name,
                location=location,
                purchase_date=purchase_datetime,
                notes=notes,
                created_by=request.user
            )

            # Create PurchaseItem records (batch items)
            total_amount = 0
            successful_items = []
            
            for item in items:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 0)
                unit_price = item.get('unit_price', 0)
                
                try:
                    product = Product.objects.get(id=product_id)
                    quantity = int(quantity)
                    unit_price = float(unit_price)
                    
                    if quantity <= 0:
                        continue
                        
                    if unit_price <= 0:
                        continue
                    
                    # Create the purchase item (batch item)
                    purchase_item = PurchaseItem.objects.create(
                        purchase=purchase,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price
                    )
                    
                    item_total = quantity * unit_price
                    total_amount += item_total
                    successful_items.append(purchase_item)
                    
                except (Product.DoesNotExist, ValueError, TypeError) as e:
                    continue

            # Update total amount
            purchase.total_amount = total_amount
            purchase.save()

            messages.success(
                request, 
                f'Purchase #{purchase.reference} created successfully! '
                f'{len(successful_items)} items added. Total: UGX {total_amount:,.0f}'
            )
            return redirect('inventory:purchase_list')
                
        except Exception as e:
            messages.error(request, f'Error creating purchase: {str(e)}')
            return render(request, 'inventory/purchase_add.html', {
                'locations': user_locations,
                'products': products,
                'suppliers': suppliers,  # ADD THIS
                'form_data': request.POST
            })

    else:
        # GET request - prepare context
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'cost_price': str(product.cost_price),
                'selling_price': str(product.selling_price),
                'category_name': product.category.name if product.category else 'Uncategorized'
            })
        
        context = {
            'locations': user_locations,
            'products': products,
            'suppliers': suppliers,  # ADD THIS LINE
            'products_json': json.dumps(products_data),
            'default_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
        }
        return render(request, 'inventory/purchase_add.html', context)


@login_required
@transaction.atomic
def purchase_delete(request, pk):
    try:
        purchase = get_object_or_404(Purchase, id=pk)
        
        # Check if user can access this purchase's location
        if not can_user_access_location(request.user, purchase.location):
            messages.error(request, "You don't have permission to delete this purchase")
            return redirect('inventory:purchase_list')
        
        if request.method == 'POST':
            # Store purchase info for message
            reference = purchase.reference
            item_count = purchase.items.count()
            
            # Reverse stock updates for all items before deleting
            for item in purchase.items.all():
                if purchase.location:
                    try:
                        # Use F() expression for atomic update
                        ProductStock.objects.filter(
                            product=item.product,
                            location=purchase.location
                        ).update(quantity=F('quantity') - item.quantity)
                    except ProductStock.DoesNotExist:
                        pass
            
            # Delete the purchase record
            purchase.delete()
            
            messages.success(
                request, 
                f"Purchase #{reference} deleted successfully! {item_count} items removed."
            )
            return redirect('inventory:purchase_list')
        
        return render(request, 'inventory/purchase_confirm_delete.html', {
            'purchase': purchase
        })
            
    except Purchase.DoesNotExist:
        messages.error(request, "Purchase not found")
        return redirect('inventory:purchase_list')
    except Exception as e:
        messages.error(request, f"Error deleting purchase: {str(e)}")
        return redirect('inventory:purchase_list')


# =======================
# SALES
# =======================
@login_required
def sale_list(request):
    """Show all sales"""
    sales = Sale.objects.all()
    sales = filter_queryset_by_user_locations(sales, request.user)
    sales = sales.select_related('customer', 'location').prefetch_related('items').order_by('-date', '-created_at')
    
    context = {
        'sales': sales,
    }
    return render(request, 'inventory/sale_list.html', context)

@login_required
@transaction.atomic
def sale_add(request):
    print('herererererererer')
    
    # Get locations from core app
    from core.models import Location
    user_locations = get_user_locations(request.user)
    
    # Get customers from transactions app
    from transactions.models import Customer
    
    if request.method == 'POST':
        print('its a post requrest')
        form = SaleForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                # Save the sale
                sale = form.save(commit=False)
                sale.created_by = request.user
                
                # Check if user can access the selected location
                if not can_user_access_location(request.user, sale.location):
                    messages.error(request, "You don't have permission to access this location")
                    return redirect('inventory:sale_add')
                
                # Set document status based on button clicked
                is_draft = 'save_draft' in request.POST
                sale.document_status = 'draft' if is_draft else 'sent'
                
                # Save sale to get ID
                sale.save()
                
                # Process sale items from the hidden field
                items_data = request.POST.get('items_data', '[]')
                items = json.loads(items_data)
                
                total_amount = 0
                for item in items:
                    product = get_object_or_404(Product, id=item['product_id'])
                    quantity = int(item['quantity'])
                    unit_price = float(item['unit_price'])
                    item_total = float(item['total'])
                    
                    # Create sale item
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=item_total
                    )
                    
                    total_amount += item_total
                    
                    # REDUCE STOCK ONLY if not a draft and not a quotation
                    if not is_draft and sale.document_type != 'quotation' and sale.location:
                        try:
                            # Use F() expression to prevent race conditions
                            updated = ProductStock.objects.filter(
                                product=product, 
                                location=sale.location,
                                quantity__gte=quantity
                            ).update(quantity=F('quantity') - quantity)
                            
                            if not updated:
                                raise ValueError(f"Not enough stock for {product.name}")
                            
                        except ProductStock.DoesNotExist:
                            raise ValueError(f"No stock found for {product.name} at {sale.location.name}")
                
                # Update sale total amount
                sale.total_amount = total_amount
                sale.save()
                
                # Success message
                status_text = "drafted" if is_draft else "created"
                messages.success(request, f"Sale {sale.document_number} {status_text} successfully!")
                
                # Redirect based on button clicked
                if 'print' in request.POST and not is_draft:
                    return redirect('inventory:print_sale', pk=sale.id)
                return redirect('inventory:sale_list')
                    
            except Exception as e:
                messages.error(request, f"Error creating sale: {str(e)}")
        else:
            # Form has errors
            messages.error(request, "Please correct the errors below.")
    
    else:
        print('its get request')
        form = SaleForm(user=request.user)
        # Set initial location to user's default
        default_location = get_user_default_location(request.user)
        if default_location:
            form.fields['location'].initial = default_location

    # Filter locations in form to only show accessible ones
    form.fields['location'].queryset = user_locations
    
    print('reaches')
    print(f'Locations count: {user_locations.count()}')
    print(f'Customers count: {Customer.objects.count()}')
    print(f'Products count: {Product.objects.count()}')
    
    return render(request, 'inventory/sale_add.html', {
        'form': form,
        'document_types': DocumentType.choices,
        'currencies': Currency.choices,
        'locations': user_locations,  # ADD THIS - locations from core app
        'customers': Customer.objects.all(),  # ADD THIS - customers from transactions app
        'products': Product.objects.all().select_related('category'),  # ADD THIS - products from inventory
        'default_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),  # ADD THIS
    })

@login_required
def api_products(request):
    """API endpoint for product search"""
    products = Product.objects.select_related('category').all()
    product_list = []
    
    for product in products:
        product_list.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'cost_price': float(product.cost_price),
            'selling_price': float(product.selling_price),
            'category_name': product.category.name if product.category else 'Uncategorized'
        })
    
    return JsonResponse({'products': product_list})


@login_required
def api_product_stock(request, product_id, location_id):
    """API endpoint for product stock at location"""
    try:
        # Check if user can access this location
        location = Location.objects.get(id=location_id)
        if not can_user_access_location(request.user, location):
            return JsonResponse({'error': 'Access denied'}, status=403)
            
        stock = ProductStock.objects.get(
            product_id=product_id,
            location_id=location_id
        )
        return JsonResponse({
            'quantity': stock.quantity,
            'product': stock.product.name,
            'location': stock.location.name
        })
    except ProductStock.DoesNotExist:
        return JsonResponse({'quantity': 0, 'product': '', 'location': ''})
    except Location.DoesNotExist:
        return JsonResponse({'error': 'Location not found'}, status=404)


@login_required
def product_search_api(request):
    """API endpoint for product search in sale form"""
    query = request.GET.get('q', '').strip()
    
    try:
        # Query products with category
        if query:
            products = Product.objects.filter(
                Q(name__icontains=query) | Q(sku__icontains=query)
            ).select_related('category')[:15]
        else:
            products = Product.objects.all().select_related('category')[:10]

        product_list = []
        for product in products:
            # Get stock quantity safely
            stock_quantity = ProductStock.objects.filter(
                product_id=product.id
            ).aggregate(total=Sum('quantity'))['total'] or 0

            product_list.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku or 'N/A',
                'selling_price': str(product.selling_price),
                'category': product.category.name if product.category else 'General',
                'stock': stock_quantity
            })

        return JsonResponse({'products': product_list})
    
    except Exception as e:
        return JsonResponse({'error': str(e), 'products': []}, status=500)


@login_required
def print_sale(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'location', 'created_by')
                    .prefetch_related('items__product'), 
        id=pk
    )
    
    # Check if user can access this sale's location
    if not can_user_access_location(request.user, sale.location):
        messages.error(request, "You don't have permission to access this sale")
        return redirect('inventory:sale_list')
    
    # Get company details
    company = CompanyDetails.objects.first()
    if not company:
        # Create default company details if they don't exist
        company = CompanyDetails.objects.create(
            name="Teba Inventory",
            address="Your company address here",
            phone="+255 XXX XXX XXX",
            email="info@teba.com"
        )
    
    # Auto-print if requested
    auto_print = request.GET.get('autoprint') == 'true'
    
    context = {
        'sale': sale,
        'company': company,
        'auto_print': auto_print,
    }
    return render(request, 'inventory/print_sale.html', context)

# =======================
# SALES REPORT (MISSING VIEW)
# =======================
@login_required
def sales_report(request):
    """Sales report with product-wise analysis"""
    # Get all sales with related data
    sales = Sale.objects.filter(document_status='sent').select_related(
        'customer', 'location'
    ).prefetch_related('items__product').order_by('-date')
    
    # Filter by user locations
    sales = filter_queryset_by_user_locations(sales, request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    category_id = request.GET.get('category', '')
    product_name = request.GET.get('product_name', '')
    customer_id = request.GET.get('customer', '')
    location_id = request.GET.get('location', '')
    
    # Apply filters
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)
    if category_id:
        sales = sales.filter(items__product__category_id=category_id).distinct()
    if product_name:
        sales = sales.filter(items__product__name__icontains=product_name).distinct()
    if customer_id:
        sales = sales.filter(customer_id=customer_id)
    if location_id:
        # Also check if user has access to this location
        try:
            location = Location.objects.get(id=location_id)
            if can_user_access_location(request.user, location):
                sales = sales.filter(location_id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Calculate product-wise sales data
    product_sales = {}
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    
    for sale in sales:
        for item in sale.items.all():
            product = item.product
            quantity = item.quantity
            revenue = item.total_price
            cost = product.cost_price * quantity
            profit = revenue - cost
            margin = (profit / revenue * 100) if revenue > 0 else 0
            
            if product.id not in product_sales:
                product_sales[product.id] = {
                    'product': product,
                    'quantity': 0,
                    'revenue': 0,
                    'cost': 0,
                    'profit': 0,
                    'margin': 0
                }
            
            product_sales[product.id]['quantity'] += quantity
            product_sales[product.id]['revenue'] += revenue
            product_sales[product.id]['cost'] += cost
            product_sales[product.id]['profit'] += profit
            
            total_revenue += revenue
            total_cost += cost
            total_profit += profit
    
    # Calculate average margin for each product
    for product_data in product_sales.values():
        if product_data['revenue'] > 0:
            product_data['margin'] = (product_data['profit'] / product_data['revenue'] * 100)
    
    # Convert to list and sort by revenue (highest first)
    product_sales_list = sorted(
        product_sales.values(), 
        key=lambda x: x['revenue'], 
        reverse=True
    )
    
    # Get filter options (filtered by user locations)
    categories = Category.objects.filter(
        product__saleitem__sale__in=sales
    ).distinct()
    
    customers = Customer.objects.filter(
        sale__in=sales
    ).distinct()
    
    locations = get_user_locations(request.user)
    
    context = {
        'product_sales': product_sales_list,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'total_margin': (total_profit / total_revenue * 100) if total_revenue > 0 else 0,
        'total_quantity': sum(item['quantity'] for item in product_sales_list),
        
        # Filter options
        'categories': categories,
        'customers': customers,
        'locations': locations,
        
        # Current filter values
        'date_from': date_from,
        'date_to': date_to,
        'category_id': category_id,
        'product_name': product_name,
        'customer_id': customer_id,
        'location_id': location_id,
    }
    
    return render(request, 'inventory/sales_report.html', context)


# =======================
# STOCK TRANSFERS
# =======================
@login_required
def transfer_list(request):
    # Get all transfer batches with their items
    transfer_batches = TransferBatch.objects.all()
    transfer_batches = filter_queryset_by_user_locations(transfer_batches, request.user, 'from_location')
    transfer_batches = transfer_batches.prefetch_related('items__product').select_related('from_location', 'to_location', 'created_by').order_by('-created_at')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    status_filter = request.GET.get('status', '')
    
    # Apply filters
    if date_from:
        transfer_batches = transfer_batches.filter(created_at__date__gte=date_from)
    if date_to:
        transfer_batches = transfer_batches.filter(created_at__date__lte=date_to)
    if location_id:
        transfer_batches = transfer_batches.filter(
            Q(from_location_id=location_id) | Q(to_location_id=location_id)
        )
    if status_filter:
        transfer_batches = transfer_batches.filter(status=status_filter)
    
    # Get statistics
    total_transfers = transfer_batches.count()
    pending_count = transfer_batches.filter(status='pending').count()
    confirmed_count = transfer_batches.filter(status='confirmed').count()
    cancelled_count = transfer_batches.filter(status='cancelled').count()
    
    # Check if any filters are active
    has_filters = any([date_from, date_to, location_id, status_filter])
    
    # Get selected location name for display
    selected_location = None
    if location_id:
        try:
            selected_location = Location.objects.get(id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Get all locations for filter dropdown
    locations = get_user_locations(request.user)
    
    context = {
        'transfer_batches': transfer_batches,
        'locations': locations,
        'selected_location': selected_location,
        'total_transfers': total_transfers,
        'pending_count': pending_count,
        'confirmed_count': confirmed_count,
        'cancelled_count': cancelled_count,
        'has_filters': has_filters,
    }
    return render(request, 'inventory/transfer_list.html', context)


@login_required
@transaction.atomic
def transfer_add(request):
    user_locations = get_user_locations(request.user)
    products = Product.objects.all().select_related('category')

    if request.method == "POST":
        from_location_id = request.POST.get('from_location')
        to_location_id = request.POST.get('to_location')
        transfer_date = request.POST.get('transfer_date')
        notes = request.POST.get('notes', '')
        items_data = request.POST.get('items_data')

        if not from_location_id or not to_location_id:
            messages.error(request, "Please select both From and To locations.")
            return redirect('inventory:transfer_add')

        if not items_data:
            messages.error(request, "Please add at least one product.")
            return redirect('inventory:transfer_add')

        try:
            from_location = Location.objects.get(id=from_location_id)
            to_location = Location.objects.get(id=to_location_id)
            
            # Check if user can access both locations
            if not can_user_access_location(request.user, from_location):
                messages.error(request, "You don't have permission to access the source location")
                return redirect('inventory:transfer_add')
                
            if not can_user_access_location(request.user, to_location):
                messages.error(request, "You don't have permission to access the destination location")
                return redirect('inventory:transfer_add')
            
            if from_location == to_location:
                messages.error(request, "Source and destination locations cannot be the same.")
                return redirect('inventory:transfer_add')
                
        except Location.DoesNotExist:
            messages.error(request, "Invalid location selected.")
            return redirect('inventory:transfer_add')

        try:
            items = json.loads(items_data)
            if not items:
                messages.error(request, "Please add at least one product.")
                return redirect('inventory:transfer_add')
        except json.JSONDecodeError:
            messages.error(request, "Invalid product data.")
            return redirect('inventory:transfer_add')

        # Parse transfer date
        try:
            if transfer_date:
                transfer_datetime = timezone.datetime.fromisoformat(transfer_date)
            else:
                transfer_datetime = timezone.now()
        except (ValueError, TypeError):
            transfer_datetime = timezone.now()

        # Create TransferBatch first
        batch = TransferBatch.objects.create(
            reference=f"TRF-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            from_location=from_location,
            to_location=to_location,
            transfer_date=transfer_datetime,
            notes=notes,
            status='pending',
            created_by=request.user
        )

        # Create StockTransfer items linked to this batch
        successful_items = []
        failed_items = []
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 0)
            
            try:
                product = Product.objects.get(id=product_id)
                quantity = int(quantity)
                
                if quantity <= 0:
                    failed_items.append({
                        'product': product.name,
                        'reason': 'Quantity must be greater than 0'
                    })
                    continue
                
                # Check stock availability
                try:
                    from_stock = ProductStock.objects.get(
                        product=product, 
                        location=from_location
                    )
                    if from_stock.quantity < quantity:
                        failed_items.append({
                            'product': product.name,
                            'reason': f'Insufficient stock. Available: {from_stock.quantity}'
                        })
                        continue
                except ProductStock.DoesNotExist:
                    failed_items.append({
                        'product': product.name,
                        'reason': f'No stock found at {from_location.name}'
                    })
                    continue
                
                # Create the transfer item
                transfer = StockTransfer.objects.create(
                    batch=batch,
                    product=product,
                    quantity=quantity,
                    transfer_date=transfer_datetime,
                    transferred_by=request.user,
                    status=StockTransfer.PENDING
                )
                successful_items.append(transfer)
                
            except Product.DoesNotExist:
                failed_items.append({
                    'product': f"ID: {product_id}",
                    'reason': 'Product not found'
                })
            except Exception as e:
                failed_items.append({
                    'product': item.get('product_name', 'Unknown'),
                    'reason': str(e)
                })

        # Show success/error messages
        if successful_items:
            total_items = len(successful_items)
            total_quantity = sum(item.quantity for item in successful_items)
            messages.success(
                request, 
                f'Transfer batch #{batch.reference} created successfully! '
                f'{total_items} items, {total_quantity} total units'
            )
        
        if failed_items:
            error_message = f'Failed to add {len(failed_items)} item(s): '
            for failed in failed_items:
                error_message += f"{failed['product']}: {failed['reason']}; "
            messages.warning(request, error_message)
        
        return redirect('inventory:transfer_list')

    else:
        # GET request - prepare context
        product_stocks = list(ProductStock.objects.filter(
            location__in=user_locations
        ).select_related('product', 'location').values(
            'product_id', 'location_id', 'quantity'
        ))
        
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'cost_price': str(product.cost_price),
                'selling_price': str(product.selling_price),
                'category_name': product.category.name if product.category else 'Uncategorized'
            })
        
        context = {
            'locations': user_locations,
            'products': products,
            'product_stocks_json': json.dumps(product_stocks),
            'products_json': json.dumps(products_data),
            'default_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
        }
        return render(request, 'inventory/transfer_add.html', context)


@login_required
@transaction.atomic
def confirm_transfer(request, batch_id):
    batch = get_object_or_404(TransferBatch, id=batch_id, status='pending')
    
    # Check if user can access the batch locations
    if not can_user_access_location(request.user, batch.from_location) or not can_user_access_location(request.user, batch.to_location):
        messages.error(request, "You don't have permission to confirm this transfer")
        return redirect('inventory:transfer_list')
    
    if request.method == 'POST':
        try:
            # Use the batch's confirm method
            batch.confirm(request.user)
            messages.success(
                request, 
                f'Transfer batch #{batch.reference} confirmed successfully! '
                f'{batch.items.count()} items processed.'
            )
            return redirect('inventory:transfer_list')
        except ValueError as e:
            messages.error(request, f'Error confirming transfer batch: {str(e)}')
            return redirect('inventory:transfer_list')
        except Exception as e:
            messages.error(request, f'Unexpected error: {str(e)}')
            return redirect('inventory:transfer_list')

    # GET request - show confirmation page with all items
    transfer_items = batch.items.select_related('product').all()
    return render(request, 'inventory/confirm_transfer.html', {
        'batch': batch,
        'transfer_items': transfer_items
    })


@login_required
@transaction.atomic
def cancel_transfer(request, batch_id):
    batch = get_object_or_404(TransferBatch, id=batch_id, status='pending')

    # Check if user can access the batch locations
    if not can_user_access_location(request.user, batch.from_location):
        messages.error(request, "You don't have permission to cancel this transfer")
        return redirect('inventory:transfer_list')

    if request.method == 'POST':
        try:
            batch.cancel()
            messages.success(
                request, 
                f'Transfer batch #{batch.reference} cancelled successfully! '
                f'{batch.items.count()} items cancelled.'
            )
            return redirect('inventory:transfer_list')
        except Exception as e:
            messages.error(request, f'Error cancelling transfer batch: {str(e)}')
            return redirect('inventory:transfer_list')

    # GET request - show cancellation page with all items
    transfer_items = batch.items.select_related('product').all()
    
    return render(request, 'inventory/cancel_transfer.html', {
        'batch': batch,
        'transfer_items': transfer_items
    })


@login_required
def transfer_detail(request, batch_id):
    """View details of a specific transfer batch"""
    batch = get_object_or_404(TransferBatch, id=batch_id)
    
    # Check if user can access the batch locations
    if not can_user_access_location(request.user, batch.from_location):
        messages.error(request, "You don't have permission to view this transfer")
        return redirect('inventory:transfer_list')
        
    transfer_items = batch.items.select_related('product').all()
    
    context = {
        'batch': batch,
        'transfer_items': transfer_items,
    }
    return render(request, 'inventory/transfer_detail.html', context)


# =======================
# STOCK REPORT
# =======================
@login_required
def stock_report(request):
    # Get all products with related data
    products = Product.objects.all().select_related('category').prefetch_related('stocks')
    
    # Get filter parameters
    search_query = request.GET.get('q', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    
    # Apply filters
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | 
            Q(sku__icontains=search_query)
        )
    
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    # Prepare product data with stock information
    product_data = []
    total_value = 0
    in_stock_count = 0
    low_stock_count = 0
    out_of_stock_count = 0
    
    user_locations = get_user_locations(request.user)
    
    for product in products:
        # Calculate total stock across user's locations only
        stocks = product.stocks.filter(location__in=user_locations)
        total_stock = sum(stock.quantity for stock in stocks)
        stock_value = total_stock * float(product.cost_price)
        total_value += stock_value
        
        # Apply status filter
        if status_filter:
            if status_filter == 'low' and not (total_stock == 0 or total_stock <= product.reorder_level):
                continue
            elif status_filter == 'out' and total_stock != 0:
                continue
            elif status_filter == 'ok' and (total_stock == 0 or total_stock <= product.reorder_level):
                continue
        
        # Apply location filter
        if location_filter:
            location_stock = product.stocks.filter(location_id=location_filter).first()
            if not location_stock or location_stock.quantity == 0:
                continue
            total_stock = location_stock.quantity
            stock_value = total_stock * float(product.cost_price)
        
        # Count stock status
        if total_stock == 0:
            out_of_stock_count += 1
        elif total_stock <= product.reorder_level:
            low_stock_count += 1
        else:
            in_stock_count += 1
        
        product_data.append({
            'product': product,
            'total_stock': total_stock,
            'stock_value': stock_value,
            'stocks': stocks
        })
    
    # Prepare summary
    summary = {
        'total_products': len(product_data),
        'in_stock': in_stock_count,
        'low_stock': low_stock_count,
        'out_of_stock': out_of_stock_count,
        'total_value': total_value,
    }
    
    # Get filter options
    categories = Category.objects.all()
    locations = user_locations
    
    context = {
        'product_data': product_data,
        'categories': categories,
        'locations': locations,
        'summary': summary,
        'search_query': search_query,
    }
    return render(request, 'inventory/stock_report.html', context)


# =======================
# CSV EXPORT/IMPORT
# =======================

@login_required
def export_products_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_import_template.csv"'

    writer = csv.writer(response)
    
    # Get user's locations for the template
    user_locations = get_user_locations(request.user)
    
    # Build dynamic header based on user's locations
    header = ['Name', 'SKU', 'Category', 'Cost Price', 'Selling Price', 'Reorder Level']
    
    # Add location quantity columns
    for i, location in enumerate(user_locations, 1):
        header.append(f'Location{i}_Quantity')
        header.append(f'Location{i}_Name')
    
    writer.writerow(header)

    # Sample data with various quantities including 0
    sample_products = []
    sample_data = [
        ['Laptop Dell XPS', 'DELL-XPS-001', 'Electronics', '1200.00', '1500.00', '5'],
        ['iPhone 15', 'APPLE-IP15-001', 'Electronics', '800.00', '999.00', '3'],
        ['Office Chair', 'CHAIR-001', 'Furniture', '150.00', '199.00', '10'],
        ['Out of Stock Item', 'OUT-OF-STOCK-001', 'General', '50.00', '75.00', '2'],  # This will have 0 stock
    ]
    
    for product_data in sample_data:
        row = product_data.copy()
        
        # Add location quantities (sample data with some zeros)
        for i, location in enumerate(user_locations, 1):
            # Vary quantities including zeros
            if product_data[0] == 'Out of Stock Item':
                sample_quantity = '0'  # Explicitly 0 for out of stock
            else:
                sample_quantity = str(10 - (i * 3))  # Some positive, some zero/negative
                if int(sample_quantity) < 0:
                    sample_quantity = '0'  # Ensure non-negative
                    
            row.append(sample_quantity)  # Quantity
            row.append(location.name)    # Location name
        
        sample_products.append(row)
    
    for product in sample_products:
        writer.writerow(product)

    return response

# =======================
# RETAIL SALES
# =======================
@login_required
def retail_sale_view(request):
    """Handle retail sales with proper validation and error handling"""
    # Import here to avoid circular imports
    from .forms import RetailSaleForm
    
    user_locations = get_user_locations(request.user)
    form = RetailSaleForm(user=request.user)
    
    if request.method == 'POST':
        form = RetailSaleForm(request.POST, user=request.user)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save()
                
                messages.success(
                    request, 
                    f"Sale completed! {sale.quantity_given:.2f} units sold for ${sale.amount_given:.2f}"
                )
                return redirect('inventory:retail_sale')
                
            except ValidationError as e:
                messages.error(request, f"Validation error: {e}")
            except ValueError as e:
                messages.error(request, f"Error: {e}")
            except Exception as e:
                messages.error(request, f"An unexpected error occurred: {e}")
    
    # Filter form locations to user's accessible locations
    form.fields['location'].queryset = user_locations
    
    context = {
        'form': form,
        'products': Product.objects.all(),
        'locations': user_locations,
        'recent_sales': RetailSale.objects.filter(
            location__in=user_locations
        ).select_related('product', 'location', 'sold_by').order_by('-sale_date')[:10]
    }
    return render(request, 'inventory/retail/retail_sale.html', context)


@login_required
def retail_sales_list(request):
    """View all retail sales with filtering options"""
    sales = RetailSale.objects.all()
    sales = filter_queryset_by_user_locations(sales, request.user)
    sales = sales.select_related('product', 'location', 'sold_by').order_by('-sale_date')
    
    # Basic filtering
    product_filter = request.GET.get('product')
    location_filter = request.GET.get('location')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if product_filter:
        sales = sales.filter(product_id=product_filter)
    if location_filter:
        sales = sales.filter(location_id=location_filter)
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)
    
    context = {
        'sales': sales,
        'products': Product.objects.all(),
        'locations': get_user_locations(request.user),
        'total_sales': sales.count(),
        'total_revenue': sum(sale.amount_given for sale in sales)
    }
    return render(request, 'inventory/retail/sales_list.html', context)


@login_required
def retail_stock_view(request):
    """View current retail stock levels"""
    user_locations = get_user_locations(request.user)
    retail_stocks = RetailStock.objects.filter(
        location__in=user_locations,
        quantity__gt=0
    ).select_related('product', 'location').order_by('product__name')
    
    context = {
        'retail_stocks': retail_stocks,
        'total_items': retail_stocks.count(),
        'total_quantity': sum(stock.quantity for stock in retail_stocks)
    }
    return render(request, 'inventory/retail/retail_stock.html', context)


@login_required
def retail_sale_detail(request, sale_id):
    """View details of a specific retail sale"""
    sale = get_object_or_404(
        RetailSale.objects.select_related('product', 'location', 'sold_by'),
        id=sale_id
    )
    
    # Check if user can access this sale's location
    if not can_user_access_location(request.user, sale.location):
        messages.error(request, "You don't have permission to view this sale")
        return redirect('inventory:retail_sales_list')
    
    context = {
        'sale': sale,
        'unit_quantity': sale.quantity_given,
        'total_value': sale.amount_given
    }
    return render(request, 'inventory/retail/sale_detail.html', context)


@login_required
@transaction.atomic
def delete_retail_sale(request, sale_id):
    """Delete a retail sale and reverse stock changes"""
    if request.method == 'POST':
        sale = get_object_or_404(RetailSale, id=sale_id)
        
        # Check if user can access this sale's location
        if not can_user_access_location(request.user, sale.location):
            messages.error(request, "You don't have permission to delete this sale")
            return redirect('inventory:retail_sales_list')
        
        try:
            # Store sale info for message
            product_name = sale.product.name
            amount = sale.amount_given
            quantity = sale.quantity_given
            
            # Manually reverse the stock operations before deleting
            # Return quantity to main stock
            main_stock = ProductStock.objects.get(
                product=sale.product,
                location=sale.location
            )
            main_stock.quantity += int(quantity)  # Convert to int for PositiveIntegerField
            main_stock.save()
            
            # Remove from retail stock
            retail_stock = RetailStock.objects.get(
                product=sale.product,
                location=sale.location
            )
            retail_stock.quantity -= quantity
            if retail_stock.quantity < 0:
                retail_stock.quantity = 0
            retail_stock.save()
            
            # Delete the sale
            sale.delete()
            
            messages.success(
                request,
                f"Sale deleted successfully. Returned {quantity:.2f} units of {product_name} to inventory."
            )
        except Exception as e:
            messages.error(request, f"Error deleting sale: {e}")
        
        return redirect('inventory:retail_sales_list')
    
    return redirect('inventory:retail_sales_list')


# API view for dynamic stock updates
@login_required
def get_product_stock(request, product_id, location_id):
    """API endpoint to get current stock for a product at a location"""
    try:
        # Check if user can access this location
        location = Location.objects.get(id=location_id)
        if not can_user_access_location(request.user, location):
            return JsonResponse({'error': 'Access denied'}, status=403)
            
        stock = ProductStock.objects.get(
            product_id=product_id,
            location_id=location_id
        )
        return JsonResponse({
            'quantity': float(stock.quantity),
            'product': stock.product.name,
            'location': stock.location.name
        })
    except ProductStock.DoesNotExist:
        return JsonResponse({'quantity': 0, 'product': '', 'location': ''}, status=404)
    except Location.DoesNotExist:
        return JsonResponse({'error': 'Location not found'}, status=404)


# =======================
# PAYMENTS
# =======================
@login_required
def add_payment(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    
    # Check if user can access this sale's location
    if not can_user_access_location(request.user, sale.location):
        messages.error(request, "You don't have permission to add payment for this sale")
        return redirect('inventory:sale_list')
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, sale=sale, user=request.user)
        if form.is_valid():
            try:
                payment = form.save()
                messages.success(request, f"Payment of {payment.amount} recorded successfully!")
                return redirect('inventory:sale_payments', sale_id=sale.id)
            except Exception as e:
                messages.error(request, f"Error recording payment: {str(e)}")
    else:
        form = PaymentForm(sale=sale, user=request.user)
        form.fields['payment_date'].initial = timezone.now()

    context = {
        'sale': sale,
        'form': form,
        'balance_due': sale.balance_due,
    }
    return render(request, 'inventory/add_payment.html', context)


from django.utils import timezone
from .forms import SalePaymentForm

def sale_payments(request, sale_id):
    """View and add payments for a specific sale"""
    sale = get_object_or_404(Sale, id=sale_id)
    payments = sale.payments.all().order_by('-payment_date')
    
    if request.method == 'POST':
        form = SalePaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.sale = sale
            payment.received_by = request.user
            
            # Validate payment amount doesn't exceed balance
            if payment.amount > sale.balance_due:
                messages.error(request, f"Payment amount (UGX {payment.amount:,.0f}) exceeds balance due (UGX {sale.balance_due:,.0f})")
            else:
                payment.save()
                
                # Update sale paid amount
                sale.paid_amount += payment.amount
                sale.save()
                
                messages.success(request, f"Payment of UGX {payment.amount:,.0f} recorded successfully!")
                return redirect('inventory:sale_payments', sale_id=sale.id)
    else:
        form = SalePaymentForm()
    
    context = {
        'sale': sale,
        'payments': payments,
        'form': form,
    }
    return render(request, 'inventory/sale_payment_form.html', context)

@login_required
def delete_payment(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    sale_id = payment.sale.id
    sale = get_object_or_404(Sale, id=sale_id)
    
    # Check if user can access this sale's location
    if not can_user_access_location(request.user, sale.location):
        messages.error(request, "You don't have permission to delete this payment")
        return redirect('inventory:sale_list')
    
    if request.method == 'POST':
        try:
            payment.delete()
            messages.success(request, "Payment deleted successfully!")
        except Exception as e:
            messages.error(request, f"Error deleting payment: {str(e)}")
    
    return redirect('inventory:sale_payments', sale_id=sale_id)


# =======================
# PURCHASE ORDERS (Multi-item)
# =======================
@login_required
def purchase_order_list(request):
    """List all purchase orders with filters"""
    purchase_orders = PurchaseOrder.objects.all()
    purchase_orders = filter_queryset_by_user_locations(purchase_orders, request.user)
    purchase_orders = purchase_orders.select_related('location', 'created_by').prefetch_related('items__product').order_by('-created_at')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')
    
    # Apply filters
    if date_from:
        purchase_orders = purchase_orders.filter(order_date__date__gte=date_from)
    if date_to:
        purchase_orders = purchase_orders.filter(order_date__date__lte=date_to)
    if location_id:
        purchase_orders = purchase_orders.filter(location_id=location_id)
    if status_filter:
        purchase_orders = purchase_orders.filter(status=status_filter)
    if supplier_filter:
        purchase_orders = purchase_orders.filter(supplier_name__icontains=supplier_filter)
    
    # Get statistics
    total_orders = purchase_orders.count()
    draft_count = purchase_orders.filter(status='draft').count()
    ordered_count = purchase_orders.filter(status='ordered').count()
    received_count = purchase_orders.filter(status='received').count()
    cancelled_count = purchase_orders.filter(status='cancelled').count()
    
    # Calculate total spent
    total_spent = sum(float(order.total_amount) for order in purchase_orders.filter(status='received'))
    
    # Check if any filters are active
    has_filters = any([date_from, date_to, location_id, status_filter, supplier_filter])
    
    # Get all locations for filter dropdown
    locations = get_user_locations(request.user)
    
    context = {
        'purchase_orders': purchase_orders,
        'locations': locations,
        'total_orders': total_orders,
        'draft_count': draft_count,
        'ordered_count': ordered_count,
        'received_count': received_count,
        'cancelled_count': cancelled_count,
        'total_spent': total_spent,
        'has_filters': has_filters,
    }
    return render(request, 'inventory/purchase_order_list.html', context)


@login_required
@transaction.atomic
def purchase_order_add(request):
    """Add new purchase order with multiple items"""
    user_locations = get_user_locations(request.user)
    products = Product.objects.all().select_related('category')
    
    if request.method == "POST":
        supplier_name = request.POST.get('supplier_name')
        location_id = request.POST.get('location')
        order_date = request.POST.get('order_date')
        expected_date = request.POST.get('expected_date')
        notes = request.POST.get('notes', '')
        items_data = request.POST.get('items_data')
        
        if not supplier_name:
            messages.error(request, "Supplier name is required")
            return redirect('inventory:purchase_order_add')
            
        if not location_id:
            messages.error(request, "Location is required")
            return redirect('inventory:purchase_order_add')

        # Check if user can access the selected location
        try:
            location = Location.objects.get(id=location_id)
            if not can_user_access_location(request.user, location):
                messages.error(request, "You don't have permission to access this location")
                return redirect('inventory:purchase_order_add')
        except Location.DoesNotExist:
            messages.error(request, "Invalid location selected")
            return redirect('inventory:purchase_order_add')

        if not items_data:
            messages.error(request, "Please add at least one product")
            return redirect('inventory:purchase_order_add')

        try:
            items = json.loads(items_data)
            if not items:
                messages.error(request, "Please add at least one product")
                return redirect('inventory:purchase_order_add')
        except json.JSONDecodeError:
            messages.error(request, "Invalid product data")
            return redirect('inventory:purchase_order_add')

        # Parse dates
        try:
            if order_date:
                order_datetime = timezone.datetime.fromisoformat(order_date)
            else:
                order_datetime = timezone.now()
        except (ValueError, TypeError):
            order_datetime = timezone.now()

        try:
            with transaction.atomic():
                # Create PurchaseOrder
                purchase_order = PurchaseOrder.objects.create(
                    supplier_name=supplier_name,
                    location=location,
                    order_date=order_datetime,
                    expected_date=expected_date if expected_date else None,
                    notes=notes,
                    status='draft',
                    created_by=request.user
                )

                # Create PurchaseOrderItem records
                total_amount = 0
                successful_items = []
                
                for item in items:
                    product_id = item.get('product_id')
                    quantity = item.get('quantity', 0)
                    unit_price = item.get('unit_price', 0)
                    
                    try:
                        product = Product.objects.get(id=product_id)
                        quantity = int(quantity)
                        unit_price = float(unit_price)
                        
                        if quantity <= 0:
                            continue
                            
                        if unit_price <= 0:
                            continue
                        
                        # Create the purchase order item
                        order_item = PurchaseOrderItem.objects.create(
                            purchase_order=purchase_order,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price
                        )
                        
                        item_total = quantity * unit_price
                        total_amount += item_total
                        successful_items.append(order_item)
                        
                    except (Product.DoesNotExist, ValueError, TypeError) as e:
                        continue

                # Update total amount
                purchase_order.total_amount = total_amount
                purchase_order.save()

                messages.success(
                    request, 
                    f'Purchase order #{purchase_order.reference} created successfully! '
                    f'{len(successful_items)} items added. Total: ${total_amount:.2f}'
                )
                return redirect('inventory:purchase_order_list')
                
        except Exception as e:
            messages.error(request, f'Error creating purchase order: {str(e)}')
            return render(request, 'inventory/purchase_order_add.html', {
                'locations': user_locations,
                'products': products,
                'form_data': request.POST
            })

    else:
        # GET request - prepare context
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'cost_price': str(product.cost_price),
                'selling_price': str(product.selling_price),
                'category_name': product.category.name if product.category else 'Uncategorized'
            })
        
        context = {
            'locations': user_locations,
            'products': products,
            'products_json': json.dumps(products_data),
            'default_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
        }
        return render(request, 'inventory/purchase_order_add.html', context)


@login_required
@transaction.atomic
def mark_purchase_received(request, order_id):
    """Mark purchase order as received and update stock"""
    purchase_order = get_object_or_404(PurchaseOrder, id=order_id, status='ordered')
    
    # Check if user can access this order's location
    if not can_user_access_location(request.user, purchase_order.location):
        messages.error(request, "You don't have permission to mark this purchase as received")
        return redirect('inventory:purchase_order_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                purchase_order.mark_received()
                messages.success(
                    request, 
                    f'Purchase order #{purchase_order.reference} marked as received! '
                    f'Stock updated for {purchase_order.items.count()} items.'
                )
                return redirect('inventory:purchase_order_list')
        except Exception as e:
            messages.error(request, f'Error marking purchase as received: {str(e)}')
            return redirect('inventory:purchase_order_list')
    
    # GET request - show confirmation page
    order_items = purchase_order.items.select_related('product').all()
    return render(request, 'inventory/mark_purchase_received.html', {
        'purchase_order': purchase_order,
        'order_items': order_items
    })


# =======================
# SALE ORDERS (Multi-item)
# =======================
@login_required
def sale_order_list(request):
    """List all sale orders with filters"""
    sale_orders = SaleOrder.objects.all()
    sale_orders = filter_queryset_by_user_locations(sale_orders, request.user)
    sale_orders = sale_orders.select_related('customer', 'location', 'created_by').prefetch_related('items__product').order_by('-created_at')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    status_filter = request.GET.get('status', '')
    customer_id = request.GET.get('customer', '')
    
    # Apply filters
    if date_from:
        sale_orders = sale_orders.filter(sale_date__date__gte=date_from)
    if date_to:
        sale_orders = sale_orders.filter(sale_date__date__lte=date_to)
    if location_id:
        sale_orders = sale_orders.filter(location_id=location_id)
    if status_filter:
        sale_orders = sale_orders.filter(status=status_filter)
    if customer_id:
        sale_orders = sale_orders.filter(customer_id=customer_id)
    
    # Get statistics
    total_orders = sale_orders.count()
    draft_count = sale_orders.filter(status='draft').count()
    confirmed_count = sale_orders.filter(status='confirmed').count()
    delivered_count = sale_orders.filter(status='delivered').count()
    cancelled_count = sale_orders.filter(status='cancelled').count()
    
    # Calculate total revenue
    total_revenue = sum(float(order.total_amount) for order in sale_orders.filter(status='confirmed'))
    
    # Check if any filters are active
    has_filters = any([date_from, date_to, location_id, status_filter, customer_id])
    
    # Get all locations and customers for filter dropdown
    locations = get_user_locations(request.user)
    customers = Customer.objects.all()
    
    context = {
        'sale_orders': sale_orders,
        'locations': locations,
        'customers': customers,
        'total_orders': total_orders,
        'draft_count': draft_count,
        'confirmed_count': confirmed_count,
        'delivered_count': delivered_count,
        'cancelled_count': cancelled_count,
        'total_revenue': total_revenue,
        'has_filters': has_filters,
    }
    return render(request, 'inventory/sale_order_list.html', context)


@login_required
@transaction.atomic
def sale_order_add(request):
    """Add new sale order with multiple items"""
    user_locations = get_user_locations(request.user)
    products = Product.objects.all().select_related('category')
    customers = Customer.objects.all()
    
    if request.method == "POST":
        customer_id = request.POST.get('customer')
        location_id = request.POST.get('location')
        sale_date = request.POST.get('sale_date')
        notes = request.POST.get('notes', '')
        items_data = request.POST.get('items_data')
        
        if not location_id:
            messages.error(request, "Location is required")
            return redirect('inventory:sale_order_add')

        # Check if user can access the selected location
        try:
            location = Location.objects.get(id=location_id)
            if not can_user_access_location(request.user, location):
                messages.error(request, "You don't have permission to access this location")
                return redirect('inventory:sale_order_add')
            customer = Customer.objects.get(id=customer_id) if customer_id else None
        except (Location.DoesNotExist, Customer.DoesNotExist):
            messages.error(request, "Invalid location or customer selected")
            return redirect('inventory:sale_order_add')

        if not items_data:
            messages.error(request, "Please add at least one product")
            return redirect('inventory:sale_order_add')

        try:
            items = json.loads(items_data)
            if not items:
                messages.error(request, "Please add at least one product")
                return redirect('inventory:sale_order_add')
        except json.JSONDecodeError:
            messages.error(request, "Invalid product data")
            return redirect('inventory:sale_order_add')

        # Parse sale date
        try:
            if sale_date:
                sale_datetime = timezone.datetime.fromisoformat(sale_date)
            else:
                sale_datetime = timezone.now()
        except (ValueError, TypeError):
            sale_datetime = timezone.now()

        try:
            with transaction.atomic():
                # Create SaleOrder
                sale_order = SaleOrder.objects.create(
                    customer=customer,
                    location=location,
                    sale_date=sale_datetime,
                    notes=notes,
                    status='draft',
                    created_by=request.user
                )

                # Create SaleOrderItem records
                total_amount = 0
                successful_items = []
                
                for item in items:
                    product_id = item.get('product_id')
                    quantity = item.get('quantity', 0)
                    unit_price = item.get('unit_price', 0)
                    
                    try:
                        product = Product.objects.get(id=product_id)
                        quantity = int(quantity)
                        unit_price = float(unit_price)
                        
                        if quantity <= 0:
                            continue
                            
                        if unit_price <= 0:
                            continue
                        
                        # Create the sale order item
                        order_item = SaleOrderItem.objects.create(
                            sale_order=sale_order,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price
                        )
                        
                        item_total = quantity * unit_price
                        total_amount += item_total
                        successful_items.append(order_item)
                        
                    except (Product.DoesNotExist, ValueError, TypeError) as e:
                        continue

                # Update total amount
                sale_order.total_amount = total_amount
                sale_order.save()

                messages.success(
                    request, 
                    f'Sale order #{sale_order.reference} created successfully! '
                    f'{len(successful_items)} items added. Total: ${total_amount:.2f}'
                )
                return redirect('inventory:sale_order_list')
                
        except Exception as e:
            messages.error(request, f'Error creating sale order: {str(e)}')
            return render(request, 'inventory/sale_order_add.html', {
                'locations': user_locations,
                'products': products,
                'customers': customers,
                'form_data': request.POST
            })

    else:
        # GET request - prepare context
        products_data = []
        for product in products:
            # Get current stock for the product in user's locations
            stock_quantity = ProductStock.objects.filter(
                product=product,
                location__in=user_locations
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            products_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'cost_price': str(product.cost_price),
                'selling_price': str(product.selling_price),
                'category_name': product.category.name if product.category else 'Uncategorized',
                'stock': stock_quantity
            })
        
        context = {
            'locations': user_locations,
            'products': products,
            'customers': customers,
            'products_json': json.dumps(products_data),
            'default_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
        }
        return render(request, 'inventory/sale_order_add.html', context)


@login_required
@transaction.atomic
def confirm_sale_order(request, order_id):
    """Confirm sale order and update stock"""
    sale_order = get_object_or_404(SaleOrder, id=order_id, status='draft')
    
    # Check if user can access this order's location
    if not can_user_access_location(request.user, sale_order.location):
        messages.error(request, "You don't have permission to confirm this sale order")
        return redirect('inventory:sale_order_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                sale_order.confirm_order()
                messages.success(
                    request, 
                    f'Sale order #{sale_order.reference} confirmed successfully! '
                    f'Stock updated for {sale_order.items.count()} items.'
                )
                return redirect('inventory:sale_order_list')
        except Exception as e:
            messages.error(request, f'Error confirming sale order: {str(e)}')
            return redirect('inventory:sale_order_list')
    
    # GET request - show confirmation page
    order_items = sale_order.items.select_related('product').all()
    
    # Check stock availability
    stock_issues = []
    for item in order_items:
        if sale_order.location:
            try:
                stock = ProductStock.objects.get(
                    product=item.product,
                    location=sale_order.location
                )
                if stock.quantity < item.quantity:
                    stock_issues.append({
                        'product': item.product.name,
                        'available': stock.quantity,
                        'requested': item.quantity
                    })
            except ProductStock.DoesNotExist:
                stock_issues.append({
                    'product': item.product.name,
                    'available': 0,
                    'requested': item.quantity
                })
    
    return render(request, 'inventory/confirm_sale_order.html', {
        'sale_order': sale_order,
        'order_items': order_items,
        'stock_issues': stock_issues
    })


# =======================
# BATCH OPERATIONS
# =======================
@login_required
@require_POST
@transaction.atomic
def product_batch_delete(request):
    product_ids = request.POST.get('product_ids', '').split(',')
    
    if not product_ids or product_ids == ['']:
        messages.error(request, "No products selected for deletion.")
        return redirect('inventory:product_list')
    
    try:
        deleted_count = 0
        for product_id in product_ids:
            try:
                product = Product.objects.get(id=product_id)
                
                # Delete associated stock records first (only in user's locations)
                user_locations = get_user_locations(request.user)
                ProductStock.objects.filter(product=product, location__in=user_locations).delete()
                
                # Delete the product
                product.delete()
                deleted_count += 1
                
            except Product.DoesNotExist:
                continue
        
        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} product(s).")
        else:
            messages.error(request, "No products were deleted.")
            
    except Exception as e:
        messages.error(request, f"Error during batch deletion: {str(e)}")
    
    return redirect('inventory:product_list')

# Add this to your inventory/views.py file

@login_required
def search_product(request):
    """Search products for autocomplete functionality"""
    query = request.GET.get('q', '').strip()
    
    try:
        # Search products by name or SKU
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(sku__icontains=query)
        ).select_related('category')[:10]
        
        product_list = []
        for product in products:
            # Get stock quantity for user's locations
            user_locations = get_user_locations(request.user)
            stock_quantity = ProductStock.objects.filter(
                product=product,
                location__in=user_locations
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            product_list.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku or 'N/A',
                'selling_price': str(product.selling_price),
                'cost_price': str(product.cost_price),
                'category': product.category.name if product.category else 'General',
                'stock': stock_quantity,
                'reorder_level': product.reorder_level,
            })
        
        return JsonResponse({'products': product_list})
        
    except Exception as e:
        return JsonResponse({'error': str(e), 'products': []}, status=500)
    
# =======================
# MISSING DELETE & EDIT VIEWS
# =======================

# =======================
# CATEGORY VIEWS
# =======================
@login_required
def category_list(request):
    categories = Category.objects.all().annotate(
        product_count=models.Count('product')
    ).order_by('name')
    
    context = {
        'categories': categories,
    }
    return render(request, 'inventory/category_list.html', context)

@login_required
def category_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        
        if not name:
            messages.error(request, "Category name is required")
            return redirect('inventory:category_add')
        
        # Check if category already exists
        if Category.objects.filter(name=name).exists():
            messages.error(request, f"Category '{name}' already exists")
            return redirect('inventory:category_add')
        
        try:
            category = Category.objects.create(
                name=name,
                description=description
            )
            messages.success(request, f"Category '{name}' added successfully!")
            return redirect('inventory:category_list')
        except Exception as e:
            messages.error(request, f"Error adding category: {str(e)}")
            return redirect('inventory:category_add')
    
    else:
        return render(request, 'inventory/category_add.html')

@login_required
def category_edit(request, pk):
    try:
        category = get_object_or_404(Category, id=pk)
        
        if request.method == 'POST':
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            
            if not name:
                messages.error(request, "Category name is required")
                return redirect('inventory:category_edit', pk=pk)
            
            # Check if name already exists (excluding current category)
            if Category.objects.filter(name=name).exclude(id=pk).exists():
                messages.error(request, f"Category '{name}' already exists")
                return redirect('inventory:category_edit', pk=pk)
            
            category.name = name
            category.description = description
            category.save()
            
            messages.success(request, f"Category '{name}' updated successfully!")
            return redirect('inventory:category_list')
        
        else:
            return render(request, 'inventory/category_edit.html', {
                'category': category
            })
            
    except Category.DoesNotExist:
        messages.error(request, "Category not found")
        return redirect('inventory:category_list')
    except Exception as e:
        messages.error(request, f"Error updating category: {str(e)}")
        return redirect('inventory:category_list')

@login_required
@require_POST
def category_delete(request, pk):
    try:
        category = get_object_or_404(Category, id=pk)
        category_name = category.name
        
        # Check if category has products
        if category.product_set.exists():
            messages.error(request, f"Cannot delete category '{category_name}' because it has products assigned to it.")
            return redirect('inventory:category_list')
        
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted successfully!")
        return redirect('inventory:category_list')
    
    except Category.DoesNotExist:
        messages.error(request, "Category not found")
        return redirect('inventory:category_list')
    except Exception as e:
        messages.error(request, f"Error deleting category: {str(e)}")
        return redirect('inventory:category_list')

# =======================
# SUPPLIER VIEWS
# =======================
@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by('name')
    
    # Manually calculate purchase counts since there's no direct FK relationship
    supplier_data = []
    for supplier in suppliers:
        # Count purchases by supplier name (since it's a CharField, not FK)
        purchase_count = Purchase.objects.filter(supplier_name=supplier.name).count()
        
        supplier_data.append({
            'supplier': supplier,
            'purchase_count': purchase_count
        })
    
    context = {
        'supplier_data': supplier_data,
    }
    return render(request, 'inventory/supplier_list.html', context)
@login_required
def supplier_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        contact_person = request.POST.get('contact_person', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        
        if not name:
            messages.error(request, "Supplier name is required")
            return redirect('inventory:supplier_add')
        
        try:
            supplier = Supplier.objects.create(
                name=name,
                contact_person=contact_person,
                email=email,
                phone=phone,
                address=address
            )
            messages.success(request, f"Supplier '{name}' added successfully!")
            return redirect('inventory:supplier_list')
        except Exception as e:
            messages.error(request, f"Error adding supplier: {str(e)}")
            return redirect('inventory:supplier_add')
    
    else:
        return render(request, 'inventory/supplier_add.html')

@login_required
def supplier_edit(request, pk):
    try:
        supplier = get_object_or_404(Supplier, id=pk)
        
        if request.method == 'POST':
            name = request.POST.get('name')
            contact_person = request.POST.get('contact_person', '')
            email = request.POST.get('email', '')
            phone = request.POST.get('phone', '')
            address = request.POST.get('address', '')
            
            if not name:
                messages.error(request, "Supplier name is required")
                return redirect('inventory:supplier_edit', pk=pk)
            
            supplier.name = name
            supplier.contact_person = contact_person
            supplier.email = email
            supplier.phone = phone
            supplier.address = address
            supplier.save()
            
            messages.success(request, f"Supplier '{name}' updated successfully!")
            return redirect('inventory:supplier_list')
        
        else:
            return render(request, 'inventory/supplier_edit.html', {
                'supplier': supplier
            })
            
    except Supplier.DoesNotExist:
        messages.error(request, "Supplier not found")
        return redirect('inventory:supplier_list')
    except Exception as e:
        messages.error(request, f"Error updating supplier: {str(e)}")
        return redirect('inventory:supplier_list')

@login_required
@require_POST
def supplier_delete(request, pk):
    try:
        supplier = get_object_or_404(Supplier, id=pk)
        supplier_name = supplier.name
        
        # Check if supplier has purchases
        if supplier.purchase_set.exists():
            messages.error(request, f"Cannot delete supplier '{supplier_name}' because it has purchase records.")
            return redirect('inventory:supplier_list')
        
        supplier.delete()
        messages.success(request, f"Supplier '{supplier_name}' deleted successfully!")
        return redirect('inventory:supplier_list')
    
    except Supplier.DoesNotExist:
        messages.error(request, "Supplier not found")
        return redirect('inventory:supplier_list')
    except Exception as e:
        messages.error(request, f"Error deleting supplier: {str(e)}")
        return redirect('inventory:supplier_list')

# =======================
# SALE DELETE & EDIT
# =======================
@login_required
@transaction.atomic
def sale_delete(request, pk):
    try:
        sale = get_object_or_404(Sale, id=pk)
        
        # Check if user can access this sale's location
        if not can_user_access_location(request.user, sale.location):
            messages.error(request, "You don't have permission to delete this sale")
            return redirect('inventory:sale_list')
        
        if request.method == 'POST':
            document_number = sale.document_number
            item_count = sale.items.count()
            
            # Return stock for all items (only if not draft and not quotation)
            if sale.document_status != 'draft' and sale.document_type != 'quotation':
                for item in sale.items.all():
                    if sale.location:
                        try:
                            # Use F() expression for atomic update
                            ProductStock.objects.filter(
                                product=item.product,
                                location=sale.location
                            ).update(quantity=F('quantity') + item.quantity)
                        except ProductStock.DoesNotExist:
                            pass
            
            # Delete the sale (this will cascade delete items due to CASCADE)
            sale.delete()
            
            messages.success(
                request, 
                f"Sale {document_number} deleted successfully! {item_count} items removed."
            )
            return redirect('inventory:sale_list')
        
        # GET request - show confirmation page
        return render(request, 'inventory/sale_confirm_delete.html', {
            'sale': sale
        })
            
    except Sale.DoesNotExist:
        messages.error(request, "Sale not found")
        return redirect('inventory:sale_list')
    except Exception as e:
        messages.error(request, f"Error deleting sale: {str(e)}")
        return redirect('inventory:sale_list')

@login_required
@transaction.atomic
def sale_edit(request, pk):
    try:
        sale = get_object_or_404(Sale, id=pk)
        
        # Check if user can access this sale's location
        if not can_user_access_location(request.user, sale.location):
            messages.error(request, "You don't have permission to edit this sale")
            return redirect('inventory:sale_list')
        
        user_locations = get_user_locations(request.user)
        
        if request.method == 'POST':
            form = SaleForm(request.POST, instance=sale, user=request.user)
            if form.is_valid():
                try:
                    updated_sale = form.save(commit=False)
                    
                    # Check if user can access the selected location
                    if not can_user_access_location(request.user, updated_sale.location):
                        messages.error(request, "You don't have permission to access this location")
                        return redirect('inventory:sale_edit', pk=pk)
                    
                    # Set document status based on button clicked
                    is_draft = 'save_draft' in request.POST
                    updated_sale.document_status = 'draft' if is_draft else 'sent'
                    
                    # Save sale first
                    updated_sale.save()
                    
                    # Process sale items from the hidden field
                    items_data = request.POST.get('items_data', '[]')
                    items = json.loads(items_data)
                    
                    # Return stock from old items
                    old_items = list(sale.items.all())
                    for old_item in old_items:
                        if sale.document_status != 'draft' and sale.document_type != 'quotation' and sale.location:
                            try:
                                ProductStock.objects.filter(
                                    product=old_item.product,
                                    location=sale.location
                                ).update(quantity=F('quantity') + old_item.quantity)
                            except ProductStock.DoesNotExist:
                                pass
                    
                    # Delete old items
                    sale.items.all().delete()
                    
                    # Create new items
                    total_amount = 0
                    for item in items:
                        product = get_object_or_404(Product, id=item['product_id'])
                        quantity = int(item['quantity'])
                        unit_price = float(item['unit_price'])
                        item_total = float(item['total'])
                        
                        # Create sale item
                        sale_item = SaleItem.objects.create(
                            sale=updated_sale,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price,
                            total_price=item_total
                        )
                        
                        total_amount += item_total
                        
                        # Reduce stock ONLY if not a draft and not a quotation
                        if not is_draft and updated_sale.document_type != 'quotation' and updated_sale.location:
                            try:
                                updated = ProductStock.objects.filter(
                                    product=product, 
                                    location=updated_sale.location,
                                    quantity__gte=quantity
                                ).update(quantity=F('quantity') - quantity)
                                
                                if not updated:
                                    raise ValueError(f"Not enough stock for {product.name}")
                                
                            except ProductStock.DoesNotExist:
                                raise ValueError(f"No stock found for {product.name} at {updated_sale.location.name}")
                    
                    # Update sale total amount
                    updated_sale.total_amount = total_amount
                    updated_sale.save()
                    
                    messages.success(request, f"Sale {updated_sale.document_number} updated successfully!")
                    return redirect('inventory:sale_list')
                    
                except Exception as e:
                    messages.error(request, f"Error updating sale: {str(e)}")
            else:
                messages.error(request, "Please correct the errors below.")
        else:
            form = SaleForm(instance=sale, user=request.user)
            # Filter locations to user's accessible ones
            form.fields['location'].queryset = user_locations
            
            # Prepare existing items data for JavaScript
            existing_items = []
            for item in sale.items.all():
                existing_items.append({
                    'product_id': item.product.id,
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'total': str(item.total_price)
                })

        return render(request, 'inventory/sale_edit.html', {
            'form': form,
            'sale': sale,
            'document_types': DocumentType.choices,
            'currencies': Currency.choices,
            'existing_items': json.dumps(existing_items) if 'existing_items' in locals() else '[]'
        })
            
    except Sale.DoesNotExist:
        messages.error(request, "Sale not found")
        return redirect('inventory:sale_list')
    except Exception as e:
        messages.error(request, f"Error loading sale edit: {str(e)}")
        return redirect('inventory:sale_list')

# =======================
# PAYMENT EDIT
# =======================
@login_required
def payment_edit(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    sale = payment.sale
    
    # Check if user can access this sale's location
    if not can_user_access_location(request.user, sale.location):
        messages.error(request, "You don't have permission to edit this payment")
        return redirect('inventory:sale_payments', sale_id=sale.id)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment, sale=sale, user=request.user)
        if form.is_valid():
            try:
                # Store old amount for stock reversal if needed
                old_amount = payment.amount
                
                # Update payment
                updated_payment = form.save()
                
                # Update sale's paid amount (this happens automatically via save method)
                messages.success(request, f"Payment updated successfully! New amount: {updated_payment.amount}")
                return redirect('inventory:sale_payments', sale_id=sale.id)
            except Exception as e:
                messages.error(request, f"Error updating payment: {str(e)}")
    else:
        form = PaymentForm(instance=payment, sale=sale, user=request.user)

    context = {
        'sale': sale,
        'payment': payment,
        'form': form,
        'balance_due': sale.balance_due,
    }
    return render(request, 'inventory/payment_edit.html', context)

# =======================
# PURCHASE EDIT
# =======================
@login_required
@transaction.atomic
def purchase_edit(request, pk):
    try:
        purchase = get_object_or_404(Purchase, id=pk)
        
        # Check if user can access this purchase's location
        if not can_user_access_location(request.user, purchase.location):
            messages.error(request, "You don't have permission to edit this purchase")
            return redirect('inventory:purchase_list')
        
        user_locations = get_user_locations(request.user)
        products = Product.objects.all().select_related('category')
        
        if request.method == 'POST':
            supplier_name = request.POST.get('supplier_name')
            location_id = request.POST.get('location')
            purchase_date = request.POST.get('purchase_date')
            notes = request.POST.get('notes', '')
            items_data = request.POST.get('items_data')

            if not supplier_name:
                messages.error(request, "Supplier name is required")
                return redirect('inventory:purchase_edit', pk=pk)
                
            if not location_id:
                messages.error(request, "Location is required")
                return redirect('inventory:purchase_edit', pk=pk)

            # Check if user can access the selected location
            try:
                location = Location.objects.get(id=location_id)
                if not can_user_access_location(request.user, location):
                    messages.error(request, "You don't have permission to access this location")
                    return redirect('inventory:purchase_edit', pk=pk)
            except Location.DoesNotExist:
                messages.error(request, "Invalid location selected")
                return redirect('inventory:purchase_edit', pk=pk)

            if not items_data:
                messages.error(request, "Please add at least one product")
                return redirect('inventory:purchase_edit', pk=pk)

            try:
                items = json.loads(items_data)
                if not items:
                    messages.error(request, "Please add at least one product")
                    return redirect('inventory:purchase_edit', pk=pk)
            except json.JSONDecodeError:
                messages.error(request, "Invalid product data")
                return redirect('inventory:purchase_edit', pk=pk)

            # Parse purchase date
            try:
                if purchase_date:
                    purchase_datetime = timezone.datetime.fromisoformat(purchase_date)
                else:
                    purchase_datetime = timezone.now()
            except (ValueError, TypeError):
                purchase_datetime = timezone.now()

            try:
                # Reverse existing stock
                for old_item in purchase.items.all():
                    if purchase.location:
                        try:
                            ProductStock.objects.filter(
                                product=old_item.product,
                                location=purchase.location
                            ).update(quantity=F('quantity') - old_item.quantity)
                        except ProductStock.DoesNotExist:
                            pass
                
                # Delete old items
                purchase.items.all().delete()
                
                # Update purchase details
                purchase.supplier_name = supplier_name
                purchase.location = location
                purchase.purchase_date = purchase_datetime
                purchase.notes = notes
                
                # Create new items
                total_amount = 0
                successful_items = []
                
                for item in items:
                    product_id = item.get('product_id')
                    quantity = item.get('quantity', 0)
                    unit_price = item.get('unit_price', 0)
                    
                    try:
                        product = Product.objects.get(id=product_id)
                        quantity = int(quantity)
                        unit_price = float(unit_price)
                        
                        if quantity <= 0:
                            continue
                            
                        if unit_price <= 0:
                            continue
                        
                        # Create the purchase item
                        purchase_item = PurchaseItem.objects.create(
                            purchase=purchase,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price
                        )
                        
                        item_total = quantity * unit_price
                        total_amount += item_total
                        successful_items.append(purchase_item)
                        
                    except (Product.DoesNotExist, ValueError, TypeError) as e:
                        continue

                # Update total amount and save
                purchase.total_amount = total_amount
                purchase.save()
                
                # Update stock with new quantities
                for item in successful_items:
                    if purchase.location:
                        try:
                            ProductStock.objects.filter(
                                product=item.product,
                                location=purchase.location
                            ).update(quantity=F('quantity') + item.quantity)
                        except ProductStock.DoesNotExist:
                            pass

                messages.success(
                    request, 
                    f'Purchase #{purchase.reference} updated successfully! '
                    f'{len(successful_items)} items. Total: ${total_amount:.2f}'
                )
                return redirect('inventory:purchase_list')
                    
            except Exception as e:
                messages.error(request, f'Error updating purchase: {str(e)}')
                return redirect('inventory:purchase_edit', pk=pk)

        else:
            # GET request - prepare context with existing data
            products_data = []
            for product in products:
                products_data.append({
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'cost_price': str(product.cost_price),
                    'selling_price': str(product.selling_price),
                    'category_name': product.category.name if product.category else 'Uncategorized'
                })
            
            # Prepare existing items data
            existing_items = []
            for item in purchase.items.all():
                existing_items.append({
                    'product_id': item.product.id,
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'total': str(item.get_total_cost())
                })
            
            context = {
                'purchase': purchase,
                'locations': user_locations,
                'products': products,
                'products_json': json.dumps(products_data),
                'existing_items': json.dumps(existing_items),
                'default_date': purchase.purchase_date.strftime('%Y-%m-%dT%H:%M'),
            }
            return render(request, 'inventory/purchase_edit.html', context)
            
    except Purchase.DoesNotExist:
        messages.error(request, "Purchase not found")
        return redirect('inventory:purchase_list')
    except Exception as e:
        messages.error(request, f"Error loading purchase edit: {str(e)}")
        return redirect('inventory:purchase_list')

# =======================
# PURCHASE ORDER DELETE
# =======================
@login_required
@transaction.atomic
def purchase_order_delete(request, pk):
    try:
        purchase_order = get_object_or_404(PurchaseOrder, id=pk)
        
        # Check if user can access this order's location
        if not can_user_access_location(request.user, purchase_order.location):
            messages.error(request, "You don't have permission to delete this purchase order")
            return redirect('inventory:purchase_order_list')
        
        if request.method == 'POST':
            reference = purchase_order.reference
            item_count = purchase_order.items.count()
            
            # Only reverse stock if order was received
            if purchase_order.status == 'received':
                for item in purchase_order.items.all():
                    if purchase_order.location:
                        try:
                            ProductStock.objects.filter(
                                product=item.product,
                                location=purchase_order.location
                            ).update(quantity=F('quantity') - item.quantity)
                        except ProductStock.DoesNotExist:
                            pass
            
            purchase_order.delete()
            
            messages.success(
                request, 
                f"Purchase order #{reference} deleted successfully! {item_count} items removed."
            )
            return redirect('inventory:purchase_order_list')
        
        return render(request, 'inventory/purchase_order_confirm_delete.html', {
            'purchase_order': purchase_order
        })
            
    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found")
        return redirect('inventory:purchase_order_list')
    except Exception as e:
        messages.error(request, f"Error deleting purchase order: {str(e)}")
        return redirect('inventory:purchase_order_list')

# =======================
# SALE ORDER DELETE
# =======================
@login_required
@transaction.atomic
def sale_order_delete(request, pk):
    try:
        sale_order = get_object_or_404(SaleOrder, id=pk)
        
        # Check if user can access this order's location
        if not can_user_access_location(request.user, sale_order.location):
            messages.error(request, "You don't have permission to delete this sale order")
            return redirect('inventory:sale_order_list')
        
        if request.method == 'POST':
            reference = sale_order.reference
            item_count = sale_order.items.count()
            
            # Return stock if order was confirmed
            if sale_order.status == 'confirmed':
                for item in sale_order.items.all():
                    if sale_order.location:
                        try:
                            ProductStock.objects.filter(
                                product=item.product,
                                location=sale_order.location
                            ).update(quantity=F('quantity') + item.quantity)
                        except ProductStock.DoesNotExist:
                            pass
            
            sale_order.delete()
            
            messages.success(
                request, 
                f"Sale order #{reference} deleted successfully! {item_count} items removed."
            )
            return redirect('inventory:sale_order_list')
        
        return render(request, 'inventory/sale_order_confirm_delete.html', {
            'sale_order': sale_order
        })
            
    except SaleOrder.DoesNotExist:
        messages.error(request, "Sale order not found")
        return redirect('inventory:sale_order_list')
    except Exception as e:
        messages.error(request, f"Error deleting sale order: {str(e)}")
        return redirect('inventory:sale_order_list')

# Add these to your inventory/views.py

@login_required
def purchase_detail(request, pk):
    """View details of a specific purchase"""
    purchase = get_object_or_404(Purchase.objects.select_related('location', 'created_by').prefetch_related('items__product'), id=pk)
    
    if not can_user_access_location(request.user, purchase.location):
        messages.error(request, "You don't have permission to view this purchase")
        return redirect('inventory:purchase_list')
    
    context = {
        'purchase': purchase,
        'items': purchase.items.all()
    }
    return render(request, 'inventory/purchase_detail.html', context)

@login_required
def purchase_order_detail(request, pk):
    """View details of a specific purchase order"""
    purchase_order = get_object_or_404(PurchaseOrder.objects.select_related('location', 'created_by').prefetch_related('items__product'), id=pk)
    
    if not can_user_access_location(request.user, purchase_order.location):
        messages.error(request, "You don't have permission to view this purchase order")
        return redirect('inventory:purchase_order_list')
    
    context = {
        'purchase_order': purchase_order,
        'items': purchase_order.items.all()
    }
    return render(request, 'inventory/purchase_order_detail.html', context)

# Add similar detail views for sale orders, etc.
@login_required
def print_purchase(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('location', 'created_by')
                       .prefetch_related('items__product'), 
        id=pk
    )
    
    if not can_user_access_location(request.user, purchase.location):
        messages.error(request, "You don't have permission to access this purchase")
        return redirect('inventory:purchase_list')
    
    company = CompanyDetails.objects.first()
    if not company:
        company = CompanyDetails.objects.create(
            name="Teba Inventory",
            address="Your company address here",
            phone="+255 XXX XXX XXX",
            email="info@teba.com"
        )
    
    context = {
        'purchase': purchase,
        'company': company,
    }
    return render(request, 'inventory/print_purchase.html', context)

@login_required
def sale_order_detail(request, pk):
    """View details of a specific sale order"""
    sale_order = get_object_or_404(
        SaleOrder.objects.select_related('customer', 'location', 'created_by')
                         .prefetch_related('items__product'), 
        id=pk
    )
    
    # Check if user can access this order's location
    if not can_user_access_location(request.user, sale_order.location):
        messages.error(request, "You don't have permission to view this sale order")
        return redirect('inventory:sale_order_list')
    
    context = {
        'sale_order': sale_order,
        'items': sale_order.items.all()
    }
    return render(request, 'inventory/sale_order_detail.html', context)

@login_required
def company_details(request):
    """View and edit company details"""
    # Get or create company details (there should only be one)
    company, created = CompanyDetails.objects.get_or_create(
        id=1,  # Ensure we only have one record
        defaults={
            'name': 'Teba Inventory',
            'address': 'Your company address here',
            'phone': '+255 XXX XXX XXX', 
            'email': 'info@teba.com'
        }
    )
    
    if request.method == 'POST':
        # Handle form submission
        company.name = request.POST.get('name', company.name)
        company.address = request.POST.get('address', company.address)
        company.phone = request.POST.get('phone', company.phone)
        company.email = request.POST.get('email', company.email)
        company.website = request.POST.get('website', company.website)
        company.tax_id = request.POST.get('tax_id', company.tax_id)
        company.bank_name = request.POST.get('bank_name', company.bank_name)
        company.bank_account = request.POST.get('bank_account', company.bank_account)
        company.bank_branch = request.POST.get('bank_branch', company.bank_branch)
        company.invoice_prefix = request.POST.get('invoice_prefix', company.invoice_prefix)
        company.quotation_prefix = request.POST.get('quotation_prefix', company.quotation_prefix)
        company.receipt_prefix = request.POST.get('receipt_prefix', company.receipt_prefix)
        company.invoice_footer = request.POST.get('invoice_footer', company.invoice_footer)
        company.quotation_footer = request.POST.get('quotation_footer', company.quotation_footer)
        
        # Handle logo upload
        if 'logo' in request.FILES:
            company.logo = request.FILES['logo']
        
        company.updated_by = request.user
        company.save()
        
        messages.success(request, 'Company details updated successfully!')
        return redirect('inventory:company_details')
    
    context = {
        'company': company,
    }
    return render(request, 'inventory/company_details.html', context)

@login_required
def import_products_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        print("🚀 === IMPORT PROCESSING START ===")
        
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        
        imported_count = 0
        updated_count = 0
        stock_updates_count = 0
        errors = []
        success_items = []
        
        # Get user's existing locations for validation
        user_locations = {loc.name: loc for loc in get_user_locations(request.user)}
        print(f"📍 User locations: {list(user_locations.keys())}")
        
        for row_num, row in enumerate(reader, start=2):
            print(f"🔍 Processing row {row_num}: {row.get('Name', 'No Name')}")
            
            try:
                # Required fields validation
                if not row.get('Name') or not row.get('SKU'):
                    errors.append(f"Row {row_num}: Name and SKU are required")
                    continue
                
                # Handle category
                category_name = row.get('Category', '').strip()
                category = None
                if category_name:
                    category, created = Category.objects.get_or_create(
                        name=category_name,
                        defaults={'description': f'Imported category: {category_name}'}
                    )
                    if created:
                        print(f"📁 Created new category: {category_name}")
                
                # Handle prices with validation - FIXED VERSION
                try:
                    # Clean cost price - remove commas and convert to float
                    cost_price_str = row.get('Cost Price', '0').strip()
                    if cost_price_str:
                        # Remove commas and any extra spaces
                        cost_price_str = cost_price_str.replace(',', '').strip()
                        cost_price = float(cost_price_str) if cost_price_str else 0
                    else:
                        cost_price = 0
                    
                    # Clean selling price - remove commas and convert to float
                    selling_price_str = row.get('Selling Price', '0').strip()
                    if selling_price_str:
                        # Remove commas and any extra spaces
                        selling_price_str = selling_price_str.replace(',', '').strip()
                        selling_price = float(selling_price_str) if selling_price_str else 0
                    else:
                        selling_price = 0
                    
                    reorder_level = int(row.get('Reorder Level', 10))
                except (ValueError, TypeError) as e:
                    errors.append(f"Row {row_num}: Invalid numeric value - {str(e)}")
                    continue
                
                # Validate prices - ALLOW PRODUCTS WITH COST PRICE BUT NO SELLING PRICE
                if cost_price < 0 or selling_price < 0:
                    errors.append(f"Row {row_num}: Prices cannot be negative")
                    continue
                
                # ONLY warn if selling price is less than cost price, but don't block import
                if selling_price > 0 and cost_price > 0 and selling_price < cost_price:
                    # Just warn but don't block import
                    errors.append(f"Row {row_num}: Warning - Selling price (${selling_price:,.2f}) is less than cost price (${cost_price:,.2f}) for '{row['Name']}'")
                    # Continue with import anyway
                
                # Auto-calculate selling price if only cost price is provided
                if cost_price > 0 and selling_price == 0:
                    selling_price = cost_price * 1.3  # 30% markup as default
                    print(f"💰 Auto-calculated selling price: ${cost_price:,.2f} -> ${selling_price:,.2f}")
                
                print(f"💰 Price validation passed: ${cost_price:,.2f} -> ${selling_price:,.2f}")
                
                # Create or update product
                product, created = Product.objects.update_or_create(
                    sku=row['SKU'],
                    defaults={
                        'name': row['Name'],
                        'category': category,
                        'cost_price': cost_price,
                        'selling_price': selling_price,
                        'reorder_level': reorder_level
                    }
                )
                
                print(f"📦 {'Created' if created else 'Updated'} product: {product.name} (SKU: {product.sku})")
                
                # Process location quantities - ALLOW ZERO QUANTITIES
                location_updates = 0
                location_details = []
                
                # Look for LocationX_Quantity and LocationX_Name columns
                for i in range(1, 20):  # Support up to 20 locations
                    quantity_key = f'Location{i}_Quantity'
                    location_name_key = f'Location{i}_Name'
                    
                    quantity_str = row.get(quantity_key, '').strip()
                    location_name = row.get(location_name_key, '').strip()
                    
                    # Skip if location name is missing, but allow quantity to be 0 or empty
                    if not location_name:
                        continue
                    
                    try:
                        # Allow zero quantities - don't skip if quantity is 0
                        quantity = int(quantity_str) if quantity_str else 0
                        
                        # Allow zero and positive quantities, but not negative
                        if quantity < 0:
                            errors.append(f"Row {row_num}: Quantity cannot be negative for {location_name}")
                            continue
                            
                        # Check if location exists and user has access
                        if location_name in user_locations:
                            location = user_locations[location_name]
                            
                            # Update or create stock record - EVEN IF QUANTITY IS 0
                            stock, stock_created = ProductStock.objects.update_or_create(
                                product=product,
                                location=location,
                                defaults={'quantity': quantity}
                            )
                            
                            location_updates += 1
                            stock_updates_count += 1
                            location_details.append(f"{location_name}: {quantity}")
                            
                            print(f"🏪 {'Created' if stock_created else 'Updated'} stock: {location_name} = {quantity}")
                            
                        else:
                            errors.append(f"Row {row_num}: Location '{location_name}' not found or no access")
                            
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid quantity '{quantity_str}' for {location_name}")
                    except Exception as e:
                        errors.append(f"Row {row_num}: Error updating stock for {location_name} - {str(e)}")
                
                if created:
                    imported_count += 1
                    success_items.append({
                        'type': 'imported',
                        'name': row['Name'],
                        'sku': row['SKU'],
                        'locations': location_details
                    })
                else:
                    updated_count += 1
                    success_items.append({
                        'type': 'updated', 
                        'name': row['Name'],
                        'sku': row['SKU'],
                        'locations': location_details
                    })
                    
                # Don't warn about zero location quantities - it's valid to have 0 stock
                if location_updates == 0:
                    print(f"ℹ️  No location quantities specified for {row['Name']} - product imported with no stock records")
                    
            except Exception as e:
                error_msg = f"Row {row_num}: Unexpected error - {str(e)}"
                print(f"❌ {error_msg}")
                errors.append(error_msg)
                continue
        
        print(f"🎯 FINAL RESULTS: {imported_count} imported, {updated_count} updated, {stock_updates_count} stock updates, {len(errors)} errors")
        
        # Store results in session for display
        request.session['import_results'] = {
            'imported_count': imported_count,
            'updated_count': updated_count,
            'stock_updates_count': stock_updates_count,
            'total_processed': imported_count + updated_count,
            'error_count': len(errors),
            'success_items': success_items[:50],
            'errors': errors[:50]
        }
        
        # Show comprehensive results
        if imported_count or updated_count or stock_updates_count:
            success_parts = []
            if imported_count:
                success_parts.append(f"{imported_count} new products")
            if updated_count:
                success_parts.append(f"{updated_count} products updated")
            if stock_updates_count:
                success_parts.append(f"{stock_updates_count} stock records updated")
            
            success_msg = f"Import completed! {', '.join(success_parts)}."
            
            if errors:
                success_msg += f" {len(errors)} warnings occurred."
            
            messages.success(request, success_msg)
            print(f"✅ {success_msg}")
        
        if errors:
            messages.warning(request, f"Import completed with {len(errors)} warnings.")
            print(f"⚠️  {len(errors)} warnings occurred")
        
        print("🚀 === IMPORT PROCESSING END ===")
        return redirect('inventory:import_products')
    
    # GET request - show import form and previous results
    import_results = request.session.pop('import_results', None)
    user_locations = get_user_locations(request.user)
    
    return render(request, 'inventory/import_products.html', {
        'import_results': import_results,
        'user_locations': user_locations,
        'location_count': len(user_locations)
    })

# =======================
# STOCKTAKE VIEWS
# =======================

@login_required
def stocktake_list(request):
    """List all stocktakes"""
    stocktakes = StockTake.objects.all()
    stocktakes = filter_queryset_by_user_locations(stocktakes, request.user)
    stocktakes = stocktakes.select_related('location', 'created_by').prefetch_related('items').order_by('-created_at')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    
    # Apply filters
    if status_filter:
        stocktakes = stocktakes.filter(status=status_filter)
    if location_filter:
        stocktakes = stocktakes.filter(location_id=location_filter)
    
    context = {
        'stocktakes': stocktakes,
        'locations': get_user_locations(request.user),
        'status_choices': StockTake.STATUS_CHOICES,
    }
    return render(request, 'inventory/stocktake_list.html', context)


@login_required
@transaction.atomic
def stocktake_create(request):
    """Create a new stocktake"""
    user_locations = get_user_locations(request.user)
    
    if request.method == 'POST':
        location_id = request.POST.get('location')
        
        if not location_id:
            messages.error(request, "Location is required")
            return redirect('inventory:stocktake_create')
        
        try:
            location = Location.objects.get(id=location_id)
            if not can_user_access_location(request.user, location):
                messages.error(request, "You don't have permission to access this location")
                return redirect('inventory:stocktake_create')
            
            # Create stocktake
            stocktake = StockTake.objects.create(
                location=location,
                created_by=request.user,
                status='draft'
            )
            
            # Get all products that have stock at this location
            products_with_stock = Product.objects.filter(
                stocks__location=location,
                stocks__quantity__gt=0
            ).distinct()
            
            # Create stocktake items
            for product in products_with_stock:
                stock = ProductStock.objects.get(product=product, location=location)
                StockTakeItem.objects.create(
                    stock_take=stocktake,
                    product=product,
                    quantity_on_hand=stock.quantity,
                    quantity_counted=None
                )
            
            messages.success(request, f"Stocktake {stocktake.reference} created successfully!")
            return redirect('inventory:stocktake_detail', pk=stocktake.id)
            
        except Location.DoesNotExist:
            messages.error(request, "Invalid location selected")
            return redirect('inventory:stocktake_create')
        except Exception as e:
            messages.error(request, f"Error creating stocktake: {str(e)}")
            return redirect('inventory:stocktake_create')
    
    context = {
        'locations': user_locations,
    }
    return render(request, 'inventory/stocktake_create.html', context)


@login_required
def stocktake_detail(request, pk):
    """View and update stocktake details"""
    stocktake = get_object_or_404(
        StockTake.objects.select_related('location', 'created_by')
                       .prefetch_related('items__product'),
        id=pk
    )
    
    if not can_user_access_location(request.user, stocktake.location):
        messages.error(request, "You don't have permission to access this stocktake")
        return redirect('inventory:stocktake_list')
    
    if request.method == 'POST':
        # Handle item updates
        for item in stocktake.items.all():
            quantity_key = f'quantity_{item.id}'
            quantity_counted = request.POST.get(quantity_key)
            
            if quantity_counted is not None:
                try:
                    item.quantity_counted = int(quantity_counted)
                    item.counted_at = timezone.now()
                    item.counted_by = request.user
                    item.save()
                except ValueError:
                    pass
        
        # Handle actions
        if 'save_draft' in request.POST:
            stocktake.status = 'draft'
            stocktake.save()
            messages.success(request, "Stocktake saved as draft")
        
        elif 'mark_in_progress' in request.POST:
            stocktake.status = 'in_progress'
            stocktake.save()
            messages.success(request, "Stocktake marked as in progress")
        
        elif 'complete' in request.POST:
            # Set uncounted items to zero first
            uncounted_items = stocktake.items.filter(quantity_counted__isnull=True)
            for item in uncounted_items:
                item.quantity_counted = 0
                item.counted_at = timezone.now()
                item.counted_by = request.user
                item.save()
            
            # Complete the stocktake
            stocktake.complete_stocktake()
            messages.success(request, f"Stocktake {stocktake.reference} completed successfully!")
        
        elif 'set_uncounted_to_zero' in request.POST:
            # Set all uncounted items to zero
            uncounted_items = stocktake.items.filter(quantity_counted__isnull=True)
            count_updated = 0
            
            for item in uncounted_items:
                item.quantity_counted = 0
                item.counted_at = timezone.now()
                item.counted_by = request.user
                item.save()
                count_updated += 1
            
            messages.success(request, f"Set {count_updated} uncounted items to zero")
        
        return redirect('inventory:stocktake_detail', pk=stocktake.id)
    
    # Calculate statistics
    total_items = stocktake.get_total_items()
    counted_items = stocktake.get_counted_items()
    uncounted_items = stocktake.get_uncounted_items()
    completion_percentage = (counted_items / total_items * 100) if total_items > 0 else 0
    
    context = {
        'stocktake': stocktake,
        'total_items': total_items,
        'counted_items': counted_items,
        'uncounted_items': uncounted_items,
        'completion_percentage': completion_percentage,
    }
    return render(request, 'inventory/stocktake_detail.html', context)


@login_required
@transaction.atomic
def stocktake_delete(request, pk):
    """Delete a stocktake"""
    stocktake = get_object_or_404(StockTake, id=pk)
    
    if not can_user_access_location(request.user, stocktake.location):
        messages.error(request, "You don't have permission to delete this stocktake")
        return redirect('inventory:stocktake_list')
    
    if request.method == 'POST':
        reference = stocktake.reference
        stocktake.delete()
        messages.success(request, f"Stocktake {reference} deleted successfully!")
        return redirect('inventory:stocktake_list')
    
    context = {
        'stocktake': stocktake,
    }
    return render(request, 'inventory/stocktake_confirm_delete.html', context)


@login_required
def set_uncounted_to_zero(request, pk):
    """API endpoint to set all uncounted items to zero"""
    stocktake = get_object_or_404(StockTake, id=pk)
    
    if not can_user_access_location(request.user, stocktake.location):
        return JsonResponse({'success': False, 'error': 'Access denied'})
    
    if request.method == 'POST':
        try:
            uncounted_items = stocktake.items.filter(quantity_counted__isnull=True)
            count_updated = 0
            
            for item in uncounted_items:
                item.quantity_counted = 0
                item.counted_at = timezone.now()
                item.counted_by = request.user
                item.save()
                count_updated += 1
            
            return JsonResponse({
                'success': True,
                'count_updated': count_updated,
                'message': f'Set {count_updated} uncounted items to zero'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


from .forms import SalePaymentForm

def sale_payments(request, sale_id):
    """View and add payments for a specific sale"""
    sale = get_object_or_404(Sale, id=sale_id)
    payments = sale.payments.all().order_by('-payment_date')
    
    if request.method == 'POST':
        form = SalePaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.sale = sale
            payment.received_by = request.user
            
            # Validate payment amount doesn't exceed balance
            if payment.amount > sale.balance_due:
                messages.error(request, f"Payment amount (UGX {payment.amount:,.0f}) exceeds balance due (UGX {sale.balance_due:,.0f})")
            else:
                payment.save()
                
                # Update sale paid amount
                sale.paid_amount += payment.amount
                sale.save()
                
                messages.success(request, f"Payment of UGX {payment.amount:,.0f} recorded successfully!")
                return redirect('inventory:sale_payments', sale_id=sale.id)
    else:
        form = SalePaymentForm()
    
    context = {
        'sale': sale,
        'payments': payments,
        'form': form,
    }
    return render(request, 'inventory/sale_payment_form.html', context)
# =======================
# COMPREHENSIVE REPORTS
# =======================

@login_required
def reports_dashboard(request):
    """Main reports dashboard with overview of all report types"""
    # Get basic statistics for the dashboard
    user_locations = get_user_locations(request.user)
    
    # Product statistics
    total_products = Product.objects.filter(
        stocks__location__in=user_locations
    ).distinct().count()
    
    low_stock_products = Product.objects.filter(
        stocks__location__in=user_locations,
        stocks__quantity__lt=F('reorder_level')
    ).distinct().count()
    
    out_of_stock_products = Product.objects.filter(
        stocks__location__in=user_locations,
        stocks__quantity=0
    ).distinct().count()
    
    # Sales statistics (last 30 days)
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    recent_sales = Sale.objects.filter(
        location__in=user_locations,
        date__gte=thirty_days_ago,
        document_status='sent'
    )
    total_sales_revenue = recent_sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_sales_count = recent_sales.count()
    
    # Purchase statistics (last 30 days)
    recent_purchases = Purchase.objects.filter(
        location__in=user_locations,
        purchase_date__gte=thirty_days_ago
    )
    total_purchase_cost = recent_purchases.aggregate(total=Sum('total_amount'))['total'] or 0
    total_purchase_count = recent_purchases.count()
    
    # Customer statistics
    customers_with_balance = Customer.objects.filter(balance__gt=0).count()
    total_customers = Customer.objects.count()
    
    context = {
        'total_products': total_products,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'total_sales_revenue': total_sales_revenue,
        'total_sales_count': total_sales_count,
        'total_purchase_cost': total_purchase_cost,
        'total_purchase_count': total_purchase_count,
        'customers_with_balance': customers_with_balance,
        'total_customers': total_customers,
    }
    return render(request, 'inventory/reports/dashboard.html', context)


@login_required
def sales_summary_report(request):
    """Comprehensive sales summary report"""
    sales = Sale.objects.filter(document_status='sent')
    sales = filter_queryset_by_user_locations(sales, request.user)
    sales = sales.select_related('customer', 'location').prefetch_related('items__product')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    customer_id = request.GET.get('customer', '')
    location_id = request.GET.get('location', '')
    group_by = request.GET.get('group_by', 'daily')  # daily, weekly, monthly, customer, product
    
    # Apply filters
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)
    if customer_id:
        sales = sales.filter(customer_id=customer_id)
    if location_id:
        try:
            location = Location.objects.get(id=location_id)
            if can_user_access_location(request.user, location):
                sales = sales.filter(location_id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Calculate summary statistics
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_cost = 0
    total_profit = 0
    
    # Calculate cost and profit
    for sale in sales:
        for item in sale.items.all():
            cost = item.product.cost_price * item.quantity
            total_cost += cost
            total_profit += item.total_price - cost
    
    total_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Group data based on selection
    if group_by == 'daily':
        grouped_data = sales.values('date__date').annotate(
            revenue=Sum('total_amount'),
            sales_count=Count('id')
        ).order_by('date__date')
    elif group_by == 'weekly':
        grouped_data = sales.extra({
            'week': "EXTRACT(WEEK FROM date)",
            'year': "EXTRACT(YEAR FROM date)"
        }).values('year', 'week').annotate(
            revenue=Sum('total_amount'),
            sales_count=Count('id')
        ).order_by('year', 'week')
    elif group_by == 'monthly':
        grouped_data = sales.extra({
            'month': "EXTRACT(MONTH FROM date)",
            'year': "EXTRACT(YEAR FROM date)"
        }).values('year', 'month').annotate(
            revenue=Sum('total_amount'),
            sales_count=Count('id')
        ).order_by('year', 'month')
    elif group_by == 'customer':
        grouped_data = sales.values('customer__name').annotate(
            revenue=Sum('total_amount'),
            sales_count=Count('id')
        ).order_by('-revenue')
    elif group_by == 'product':
        # Need to go through SaleItem for product-level grouping
        sale_items = SaleItem.objects.filter(sale__in=sales).values(
            'product__name'
        ).annotate(
            revenue=Sum('total_price'),
            quantity_sold=Sum('quantity'),
            sales_count=Count('sale', distinct=True)
        ).order_by('-revenue')
        grouped_data = list(sale_items)
    else:
        grouped_data = []
    
    # Top performing products
    top_products = SaleItem.objects.filter(sale__in=sales).values(
        'product__name'
    ).annotate(
        revenue=Sum('total_price'),
        quantity_sold=Sum('quantity'),
        profit=Sum(F('total_price') - F('product__cost_price') * F('quantity'))
    ).order_by('-revenue')[:10]
    
    # Sales trend (last 12 months)
    twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
    monthly_trend = sales.filter(date__gte=twelve_months_ago).extra({
        'month': "EXTRACT(MONTH FROM date)",
        'year': "EXTRACT(YEAR FROM date)"
    }).values('year', 'month').annotate(
        revenue=Sum('total_amount'),
        sales_count=Count('id')
    ).order_by('year', 'month')
    
    context = {
        'sales': sales,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'total_margin': total_margin,
        'grouped_data': grouped_data,
        'top_products': top_products,
        'monthly_trend': monthly_trend,
        'group_by': group_by,
        
        # Filter options
        'customers': Customer.objects.all(),
        'locations': get_user_locations(request.user),
        
        # Current filter values
        'date_from': date_from,
        'date_to': date_to,
        'customer_id': customer_id,
        'location_id': location_id,
    }
    return render(request, 'inventory/reports/sales_summary.html', context)


@login_required
def product_performance_report(request):
    """Detailed product performance and profitability report"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    category_id = request.GET.get('category', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    min_sales = request.GET.get('min_sales', 0)
    sort_by = request.GET.get('sort_by', 'revenue')
    
    try:
        min_sales = int(min_sales)
    except ValueError:
        min_sales = 0
    
    # Get sales data with filters
    sales = Sale.objects.filter(
        document_status='sent',
        location__in=user_locations
    )
    
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)
    
    # Get product performance data
    products = Product.objects.all()
    if category_id:
        products = products.filter(category_id=category_id)
    
    product_performance = []
    
    for product in products:
        # Get sales data for this product
        sale_items = SaleItem.objects.filter(
            sale__in=sales,
            product=product
        )
        
        total_sold = sale_items.aggregate(total=Sum('quantity'))['total'] or 0
        total_revenue = sale_items.aggregate(total=Sum('total_price'))['total'] or 0
        total_cost = product.cost_price * total_sold
        total_profit = total_revenue - total_cost
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Get current stock
        current_stock = ProductStock.objects.filter(
            product=product,
            location__in=user_locations
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Calculate sell-through rate (if we have purchase data)
        total_purchased = PurchaseItem.objects.filter(
            product=product,
            purchase__location__in=user_locations
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        sell_through_rate = (total_sold / total_purchased * 100) if total_purchased > 0 else 0
        
        # Only include products that meet minimum sales threshold
        if total_sold >= min_sales:
            product_performance.append({
                'product': product,
                'total_sold': total_sold,
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'profit_margin': profit_margin,
                'current_stock': current_stock,
                'sell_through_rate': sell_through_rate,
                'stock_turnover': total_sold / current_stock if current_stock > 0 else 0,
            })
    
    # Sort the results
    sort_options = {
        'revenue': lambda x: x['total_revenue'],
        'profit': lambda x: x['total_profit'],
        'margin': lambda x: x['profit_margin'],
        'quantity': lambda x: x['total_sold'],
        'turnover': lambda x: x['stock_turnover'],
    }
    
    if sort_by in sort_options:
        product_performance.sort(key=sort_options[sort_by], reverse=True)
    
    # Summary statistics
    total_revenue = sum(item['total_revenue'] for item in product_performance)
    total_profit = sum(item['total_profit'] for item in product_performance)
    total_units_sold = sum(item['total_sold'] for item in product_performance)
    avg_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Identify best and worst performers
    best_performers = sorted(product_performance, key=lambda x: x['total_profit'], reverse=True)[:5]
    worst_performers = sorted(product_performance, key=lambda x: x['total_profit'])[:5]
    
    context = {
        'product_performance': product_performance,
        'categories': Category.objects.all(),
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_units_sold': total_units_sold,
        'avg_margin': avg_margin,
        'best_performers': best_performers,
        'worst_performers': worst_performers,
        
        # Filter values
        'category_id': category_id,
        'date_from': date_from,
        'date_to': date_to,
        'min_sales': min_sales,
        'sort_by': sort_by,
    }
    return render(request, 'inventory/reports/product_performance.html', context)


@login_required
def inventory_valuation_report(request):
    """Inventory valuation and stock analysis report"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    category_id = request.GET.get('category', '')
    stock_status = request.GET.get('stock_status', 'all')  # all, low, out, excess
    location_id = request.GET.get('location', '')
    
    # Get products with their stock information
    products = Product.objects.all()
    
    if category_id:
        products = products.filter(category_id=category_id)
    
    inventory_data = []
    total_valuation = 0
    total_items = 0
    low_stock_count = 0
    out_of_stock_count = 0
    excess_stock_count = 0
    
    for product in products:
        # Get stock across all user locations or specific location
        if location_id:
            stocks = ProductStock.objects.filter(
                product=product,
                location_id=location_id
            )
        else:
            stocks = ProductStock.objects.filter(
                product=product,
                location__in=user_locations
            )
        
        total_quantity = stocks.aggregate(total=Sum('quantity'))['total'] or 0
        valuation = total_quantity * float(product.cost_price)
        
        # Determine stock status
        status = 'normal'
        if total_quantity == 0:
            status = 'out_of_stock'
            out_of_stock_count += 1
        elif total_quantity <= product.reorder_level:
            status = 'low_stock'
            low_stock_count += 1
        elif total_quantity > (product.reorder_level * 3):  # Consider excess if 3x reorder level
            status = 'excess_stock'
            excess_stock_count += 1
        
        # Apply stock status filter
        if stock_status != 'all':
            if stock_status == 'low' and status != 'low_stock':
                continue
            elif stock_status == 'out' and status != 'out_of_stock':
                continue
            elif stock_status == 'excess' and status != 'excess_stock':
                continue
            elif stock_status == 'normal' and status != 'normal':
                continue
        
        inventory_data.append({
            'product': product,
            'total_quantity': total_quantity,
            'valuation': valuation,
            'status': status,
            'reorder_level': product.reorder_level,
            'stocks': stocks,  # Include individual location stocks
        })
        
        total_valuation += valuation
        total_items += 1
    
    # Sort by valuation (highest first)
    inventory_data.sort(key=lambda x: x['valuation'], reverse=True)
    
    # Category-wise breakdown
    category_breakdown = {}
    for item in inventory_data:
        category_name = item['product'].category.name if item['product'].category else 'Uncategorized'
        if category_name not in category_breakdown:
            category_breakdown[category_name] = {
                'count': 0,
                'valuation': 0,
                'percentage': 0
            }
        
        category_breakdown[category_name]['count'] += 1
        category_breakdown[category_name]['valuation'] += item['valuation']
    
    # Calculate percentages
    for category in category_breakdown:
        category_breakdown[category]['percentage'] = (
            category_breakdown[category]['valuation'] / total_valuation * 100
        ) if total_valuation > 0 else 0
    
    context = {
        'inventory_data': inventory_data,
        'categories': Category.objects.all(),
        'locations': get_user_locations(request.user),
        'total_valuation': total_valuation,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'excess_stock_count': excess_stock_count,
        'category_breakdown': category_breakdown,
        
        # Filter values
        'category_id': category_id,
        'stock_status': stock_status,
        'location_id': location_id,
    }
    return render(request, 'inventory/reports/inventory_valuation.html', context)


@login_required
def purchase_analysis_report(request):
    """Purchase analysis and supplier performance report"""
    purchases = Purchase.objects.all()
    purchases = filter_queryset_by_user_locations(purchases, request.user)
    purchases = purchases.select_related('location').prefetch_related('items__product')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    supplier_name = request.GET.get('supplier', '')
    location_id = request.GET.get('location', '')
    
    # Apply filters
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    if supplier_name:
        purchases = purchases.filter(supplier_name__icontains=supplier_name)
    if location_id:
        try:
            location = Location.objects.get(id=location_id)
            if can_user_access_location(request.user, location):
                purchases = purchases.filter(location_id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Calculate supplier performance
    supplier_performance = {}
    total_spent = 0
    total_items = 0
    
    for purchase in purchases:
        supplier = purchase.supplier_name
        if supplier not in supplier_performance:
            supplier_performance[supplier] = {
                'total_spent': 0,
                'order_count': 0,
                'total_items': 0,
                'avg_order_value': 0,
                'last_order_date': purchase.purchase_date
            }
        
        supplier_performance[supplier]['total_spent'] += float(purchase.total_amount)
        supplier_performance[supplier]['order_count'] += 1
        supplier_performance[supplier]['total_items'] += purchase.get_total_quantity()
        
        if purchase.purchase_date > supplier_performance[supplier]['last_order_date']:
            supplier_performance[supplier]['last_order_date'] = purchase.purchase_date
        
        total_spent += float(purchase.total_amount)
        total_items += purchase.get_total_quantity()
    
    # Calculate average order value for each supplier
    for supplier in supplier_performance:
        supplier_performance[supplier]['avg_order_value'] = (
            supplier_performance[supplier]['total_spent'] / 
            supplier_performance[supplier]['order_count']
        )
    
    # Convert to list and sort by total spent
    supplier_list = [
        {
            'name': supplier,
            **data
        }
        for supplier, data in supplier_performance.items()
    ]
    supplier_list.sort(key=lambda x: x['total_spent'], reverse=True)
    
    # Monthly purchase trend
    twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
    monthly_trend = purchases.filter(purchase_date__gte=twelve_months_ago).extra({
        'month': "EXTRACT(MONTH FROM purchase_date)",
        'year': "EXTRACT(YEAR FROM purchase_date)"
    }).values('year', 'month').annotate(
        total_spent=Sum('total_amount'),
        order_count=Count('id')
    ).order_by('year', 'month')
    
    # Top purchased products
    top_products = PurchaseItem.objects.filter(purchase__in=purchases).values(
        'product__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_cost=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total_quantity')[:10]
    
    context = {
        'purchases': purchases,
        'supplier_performance': supplier_list,
        'monthly_trend': monthly_trend,
        'top_products': top_products,
        'total_spent': total_spent,
        'total_items': total_items,
        'supplier_count': len(supplier_list),
        
        # Filter options
        'locations': get_user_locations(request.user),
        'unique_suppliers': list(set(purchase.supplier_name for purchase in purchases if purchase.supplier_name)),
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'supplier_name': supplier_name,
        'location_id': location_id,
    }
    return render(request, 'inventory/reports/purchase_analysis.html', context)


@login_required
def customer_analysis_report(request):
    """Customer purchasing behavior and profitability analysis"""
    sales = Sale.objects.filter(document_status='sent')
    sales = filter_queryset_by_user_locations(sales, request.user)
    sales = sales.select_related('customer', 'location').prefetch_related('items__product')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    min_orders = request.GET.get('min_orders', 1)
    location_id = request.GET.get('location', '')
    
    try:
        min_orders = int(min_orders)
    except ValueError:
        min_orders = 1
    
    # Apply filters
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)
    if location_id:
        try:
            location = Location.objects.get(id=location_id)
            if can_user_access_location(request.user, location):
                sales = sales.filter(location_id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Calculate customer performance
    customer_performance = {}
    
    for sale in sales:
        customer = sale.customer
        if not customer:
            continue
            
        if customer.id not in customer_performance:
            customer_performance[customer.id] = {
                'customer': customer,
                'total_spent': 0,
                'order_count': 0,
                'avg_order_value': 0,
                'first_order_date': sale.date,
                'last_order_date': sale.date,
                'products_purchased': set(),
                'total_profit': 0
            }
        
        customer_data = customer_performance[customer.id]
        customer_data['total_spent'] += float(sale.total_amount)
        customer_data['order_count'] += 1
        
        # Calculate profit for this sale
        sale_profit = 0
        for item in sale.items.all():
            cost = item.product.cost_price * item.quantity
            sale_profit += item.total_price - cost
            customer_data['products_purchased'].add(item.product.name)
        
        customer_data['total_profit'] += sale_profit
        
        # Update dates
        if sale.date < customer_data['first_order_date']:
            customer_data['first_order_date'] = sale.date
        if sale.date > customer_data['last_order_date']:
            customer_data['last_order_date'] = sale.date
    
    # Calculate averages and convert sets to counts
    customer_list = []
    for customer_id, data in customer_performance.items():
        if data['order_count'] >= min_orders:
            data['avg_order_value'] = data['total_spent'] / data['order_count']
            data['products_count'] = len(data['products_purchased'])
            data['profit_margin'] = (data['total_profit'] / data['total_spent'] * 100) if data['total_spent'] > 0 else 0
            
            # Calculate customer lifetime (in days)
            lifetime_days = (data['last_order_date'] - data['first_order_date']).days
            data['lifetime_days'] = max(lifetime_days, 1)  # Avoid division by zero
            
            # Calculate average days between orders
            data['avg_days_between_orders'] = data['lifetime_days'] / data['order_count'] if data['order_count'] > 1 else 0
            
            customer_list.append(data)
    
    # Sort options
    sort_by = request.GET.get('sort_by', 'total_spent')
    sort_options = {
        'total_spent': lambda x: x['total_spent'],
        'order_count': lambda x: x['order_count'],
        'avg_order_value': lambda x: x['avg_order_value'],
        'total_profit': lambda x: x['total_profit'],
        'profit_margin': lambda x: x['profit_margin'],
    }
    
    if sort_by in sort_options:
        customer_list.sort(key=sort_options[sort_by], reverse=True)
    
    # Customer segmentation
    segments = {
        'vip': [],  # Top 20% by spending
        'regular': [],  # Middle 60%
        'occasional': [],  # Bottom 20%
    }
    
    if customer_list:
        # Sort by total spent for segmentation
        sorted_by_spent = sorted(customer_list, key=lambda x: x['total_spent'], reverse=True)
        total_customers = len(sorted_by_spent)
        
        vip_count = max(1, int(total_customers * 0.2))  # At least 1 customer
        regular_count = int(total_customers * 0.6)
        
        segments['vip'] = sorted_by_spent[:vip_count]
        segments['regular'] = sorted_by_spent[vip_count:vip_count + regular_count]
        segments['occasional'] = sorted_by_spent[vip_count + regular_count:]
    
    # Summary statistics
    total_revenue = sum(customer['total_spent'] for customer in customer_list)
    total_profit = sum(customer['total_profit'] for customer in customer_list)
    total_customers = len(customer_list)
    avg_customer_value = total_revenue / total_customers if total_customers > 0 else 0
    
    context = {
        'customer_performance': customer_list,
        'customer_segments': segments,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_customers': total_customers,
        'avg_customer_value': avg_customer_value,
        
        # Filter options
        'locations': get_user_locations(request.user),
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'min_orders': min_orders,
        'location_id': location_id,
        'sort_by': sort_by,
    }
    return render(request, 'inventory/reports/customer_analysis.html', context)


@login_required
def stock_movement_report(request):
    """Stock movement and turnover analysis"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    product_id = request.GET.get('product', '')
    category_id = request.GET.get('category', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    
    # Base date range (last 90 days if not specified)
    if not date_from:
        date_from = (timezone.now() - timezone.timedelta(days=90)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = timezone.now().strftime('%Y-%m-%d')
    
    # Convert dates for filtering
    try:
        start_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
        end_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        start_date = timezone.now().date() - timezone.timedelta(days=90)
        end_date = timezone.now().date()
    
    # Get products with filters
    products = Product.objects.all()
    if product_id:
        products = products.filter(id=product_id)
    if category_id:
        products = products.filter(category_id=category_id)
    
    stock_movement_data = []
    
    for product in products:
        # Get sales in period
        sales_items = SaleItem.objects.filter(
            sale__document_status='sent',
            sale__location__in=user_locations,
            sale__date__date__range=[start_date, end_date],
            product=product
        )
        
        if location_id:
            sales_items = sales_items.filter(sale__location_id=location_id)
        
        total_sold = sales_items.aggregate(total=Sum('quantity'))['total'] or 0
        sales_revenue = sales_items.aggregate(total=Sum('total_price'))['total'] or 0
        
        # Get purchases in period
        purchase_items = PurchaseItem.objects.filter(
            purchase__location__in=user_locations,
            purchase__purchase_date__date__range=[start_date, end_date],
            product=product
        )
        
        if location_id:
            purchase_items = purchase_items.filter(purchase__location_id=location_id)
        
        total_purchased = purchase_items.aggregate(total=Sum('quantity'))['total'] or 0
        purchase_cost = purchase_items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0
        
        # Get transfers in period
        transfers_out = StockTransfer.objects.filter(
            batch__from_location__in=user_locations,
            transfer_date__date__range=[start_date, end_date],
            product=product,
            status='completed'
        )
        
        transfers_in = StockTransfer.objects.filter(
            batch__to_location__in=user_locations,
            transfer_date__date__range=[start_date, end_date],
            product=product,
            status='completed'
        )
        
        if location_id:
            transfers_out = transfers_out.filter(batch__from_location_id=location_id)
            transfers_in = transfers_in.filter(batch__to_location_id=location_id)
        
        total_transferred_out = transfers_out.aggregate(total=Sum('quantity'))['total'] or 0
        total_transferred_in = transfers_in.aggregate(total=Sum('quantity'))['total'] or 0
        
        # Get current stock
        stocks_query = ProductStock.objects.filter(
            product=product,
            location__in=user_locations
        )
        if location_id:
            stocks_query = stocks_query.filter(location_id=location_id)
        
        current_stock = stocks_query.aggregate(total=Sum('quantity'))['total'] or 0
        
        # Calculate net movement
        net_movement = total_purchased + total_transferred_in - total_sold - total_transferred_out
        
        # Calculate stock turnover rate
        avg_stock = current_stock  # Simplified - in reality should be average over period
        turnover_rate = (total_sold / avg_stock) if avg_stock > 0 else 0
        
        # Calculate days of inventory
        avg_daily_sales = total_sold / ((end_date - start_date).days + 1) if (end_date - start_date).days > 0 else 0
        days_of_inventory = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else 0
        
        stock_movement_data.append({
            'product': product,
            'current_stock': current_stock,
            'total_sold': total_sold,
            'total_purchased': total_purchased,
            'total_transferred_out': total_transferred_out,
            'total_transferred_in': total_transferred_in,
            'net_movement': net_movement,
            'sales_revenue': sales_revenue,
            'purchase_cost': purchase_cost,
            'turnover_rate': turnover_rate,
            'days_of_inventory': days_of_inventory,
        })
    
    # Sort by various criteria
    sort_by = request.GET.get('sort_by', 'sales_revenue')
    sort_options = {
        'sales_revenue': lambda x: x['sales_revenue'],
        'turnover_rate': lambda x: x['turnover_rate'],
        'current_stock': lambda x: x['current_stock'],
        'net_movement': lambda x: x['net_movement'],
        'days_of_inventory': lambda x: x['days_of_inventory'],
    }
    
    if sort_by in sort_options:
        stock_movement_data.sort(key=sort_options[sort_by], reverse=True)
    
    # Identify fast and slow movers
    fast_movers = [item for item in stock_movement_data if item['turnover_rate'] > 2]
    slow_movers = [item for item in stock_movement_data if item['turnover_rate'] < 0.5 and item['current_stock'] > 0]
    
    context = {
        'stock_movement_data': stock_movement_data,
        'fast_movers': fast_movers,
        'slow_movers': slow_movers,
        'products': Product.objects.all(),
        'categories': Category.objects.all(),
        'locations': get_user_locations(request.user),
        'date_from': date_from,
        'date_to': date_to,
        'product_id': product_id,
        'category_id': category_id,
        'location_id': location_id,
        'sort_by': sort_by,
    }
    return render(request, 'inventory/reports/stock_movement.html', context)


@login_required
def export_report_csv(request, report_type):
    """Export various reports to CSV"""
    # This is a simplified version - you would need to implement
    # the actual data fetching and CSV generation for each report type
    
    response = HttpResponse(content_type='text/csv')
    
    if report_type == 'sales_summary':
        filename = f'sales_summary_{timezone.now().strftime("%Y%m%d")}.csv'
        # Implement sales summary CSV export
        pass
    elif report_type == 'product_performance':
        filename = f'product_performance_{timezone.now().strftime("%Y%m%d")}.csv'
        # Implement product performance CSV export
        pass
    # Add other report types...
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # For now, return a simple response
    writer = csv.writer(response)
    writer.writerow(['Report', 'Date', 'Status'])
    writer.writerow([report_type, timezone.now().strftime('%Y-%m-%d'), 'Generated'])
    
    return response

@login_required
def customer_search_api(request):
    """API endpoint for customer search in sale form - fetches from transactions app"""
    query = request.GET.get('q', '').strip()
    
    try:
        # Import from transactions app
        from transactions.models import Customer
        
        if query:
            customers = Customer.objects.filter(
                Q(name__icontains=query) | 
                Q(phone__icontains=query) |
                Q(email__icontains=query)
            )[:15]
        else:
            customers = Customer.objects.all()[:10]

        customer_list = []
        for customer in customers:
            customer_list.append({
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone or 'N/A',
                'email': customer.email or 'N/A',
                'balance': float(customer.balance)
            })

        return JsonResponse({'customers': customer_list})
    
    except Exception as e:
        return JsonResponse({'error': str(e), 'customers': []}, status=500)
    
    # Add this to your inventory/views.py

@login_required
def product_movement_report(request, product_id):
    """Comprehensive product movement report showing complete history"""
    product = get_object_or_404(Product, id=product_id)
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    transaction_type = request.GET.get('type', 'all')
    
    # Apply date filters
    date_filter = Q()
    if date_from:
        date_filter &= Q(date__gte=date_from)
    if date_to:
        date_filter &= Q(date__lte=date_to)
    
    # Get all movements data
    
    # 1. PURCHASES
    purchase_items = PurchaseItem.objects.filter(
        product=product,
        purchase__location__in=user_locations
    ).select_related('purchase', 'purchase__location')
    
    if date_from or date_to:
        purchase_items = purchase_items.filter(
            purchase__purchase_date__date__gte=date_from if date_from else '1900-01-01',
            purchase__purchase_date__date__lte=date_to if date_to else '2100-12-31'
        )
    
    if location_id:
        purchase_items = purchase_items.filter(purchase__location_id=location_id)
    
    # 2. SALES
    sale_items = SaleItem.objects.filter(
        product=product,
        sale__location__in=user_locations
    ).select_related('sale', 'sale__customer', 'sale__location')
    
    if date_from or date_to:
        sale_items = sale_items.filter(
            sale__date__date__gte=date_from if date_from else '1900-01-01',
            sale__date__date__lte=date_to if date_to else '2100-12-31'
        )
    
    if location_id:
        sale_items = sale_items.filter(sale__location_id=location_id)
    
    # 3. TRANSFERS OUT (from user's locations)
    transfers_out = StockTransfer.objects.filter(
        product=product,
        batch__from_location__in=user_locations,
        status='completed'
    ).select_related('batch__from_location', 'batch__to_location', 'transferred_by')
    
    if date_from or date_to:
        transfers_out = transfers_out.filter(
            transfer_date__date__gte=date_from if date_from else '1900-01-01',
            transfer_date__date__lte=date_to if date_to else '2100-12-31'
        )
    
    if location_id:
        transfers_out = transfers_out.filter(batch__from_location_id=location_id)
    
    # 4. TRANSFERS IN (to user's locations)
    transfers_in = StockTransfer.objects.filter(
        product=product,
        batch__to_location__in=user_locations,
        status='completed'
    ).select_related('batch__from_location', 'batch__to_location', 'transferred_by')
    
    if date_from or date_to:
        transfers_in = transfers_in.filter(
            transfer_date__date__gte=date_from if date_from else '1900-01-01',
            transfer_date__date__lte=date_to if date_to else '2100-12-31'
        )
    
    if location_id:
        transfers_in = transfers_in.filter(batch__to_location_id=location_id)
    
    # 5. STOCKTAKE ADJUSTMENTS
    stocktake_items = StockTakeItem.objects.filter(
        product=product,
        stock_take__location__in=user_locations,
        stock_take__status='completed'
    ).select_related('stock_take', 'stock_take__location', 'counted_by')
    
    if date_from or date_to:
        stocktake_items = stocktake_items.filter(
            stock_take__created_at__date__gte=date_from if date_from else '1900-01-01',
            stock_take__created_at__date__lte=date_to if date_to else '2100-12-31'
        )
    
    if location_id:
        stocktake_items = stocktake_items.filter(stock_take__location_id=location_id)
    
    # Combine all movements into a single timeline
    movements = []
    
    # Add purchases
    for item in purchase_items:
        movements.append({
            'date': item.purchase.purchase_date,
            'type': 'purchase',
            'reference': item.purchase.reference,
            'quantity': item.quantity,
            'in_out': 'in',
            'location': item.purchase.location,
            'unit_price': item.unit_price,
            'total_value': item.quantity * item.unit_price,
            'related_object': item.purchase,
            'description': f'Purchase from {item.purchase.supplier_name}'
        })
    
    # Add sales
    for item in sale_items:
        movements.append({
            'date': item.sale.date,
            'type': 'sale',
            'reference': item.sale.document_number,
            'quantity': item.quantity,
            'in_out': 'out',
            'location': item.sale.location,
            'unit_price': item.unit_price,
            'total_value': item.total_price,
            'related_object': item.sale,
            'description': f'Sale to {item.sale.customer.name if item.sale.customer else "Walk-in Customer"}'
        })
    
    # Add transfers out
    for transfer in transfers_out:
        movements.append({
            'date': transfer.transfer_date,
            'type': 'transfer_out',
            'reference': transfer.batch.reference,
            'quantity': transfer.quantity,
            'in_out': 'out',
            'location': transfer.batch.from_location,
            'unit_price': product.cost_price,
            'total_value': transfer.quantity * product.cost_price,
            'related_object': transfer.batch,
            'description': f'Transfer to {transfer.batch.to_location.name}'
        })
    
    # Add transfers in
    for transfer in transfers_in:
        movements.append({
            'date': transfer.transfer_date,
            'type': 'transfer_in',
            'reference': transfer.batch.reference,
            'quantity': transfer.quantity,
            'in_out': 'in',
            'location': transfer.batch.to_location,
            'unit_price': product.cost_price,
            'total_value': transfer.quantity * product.cost_price,
            'related_object': transfer.batch,
            'description': f'Transfer from {transfer.batch.from_location.name}'
        })
    
    # Add stocktake adjustments
    for item in stocktake_items:
        if item.quantity_counted is not None and item.quantity_on_hand is not None:
            adjustment = item.quantity_counted - item.quantity_on_hand
            if adjustment != 0:  # Only include actual adjustments
                movements.append({
                    'date': item.counted_at or item.stock_take.created_at,
                    'type': 'adjustment',
                    'reference': item.stock_take.reference,
                    'quantity': abs(adjustment),
                    'in_out': 'in' if adjustment > 0 else 'out',
                    'location': item.stock_take.location,
                    'unit_price': product.cost_price,
                    'total_value': abs(adjustment) * product.cost_price,
                    'related_object': item.stock_take,
                    'description': f'Stocktake adjustment ({adjustment:+d})'
                })
    
    # Apply transaction type filter
    if transaction_type != 'all':
        movements = [m for m in movements if m['type'] == transaction_type]
    
    # Sort by date (most recent first)
    movements.sort(key=lambda x: x['date'], reverse=True)
    
    # Calculate summary statistics
    total_in = sum(m['quantity'] for m in movements if m['in_out'] == 'in')
    total_out = sum(m['quantity'] for m in movements if m['in_out'] == 'out')
    net_movement = total_in - total_out
    
    total_in_value = sum(m['total_value'] for m in movements if m['in_out'] == 'in')
    total_out_value = sum(m['total_value'] for m in movements if m['in_out'] == 'out')
    net_value_movement = total_in_value - total_out_value
    
    # Get current stock
    current_stock_query = ProductStock.objects.filter(
        product=product,
        location__in=user_locations
    )
    if location_id:
        current_stock_query = current_stock_query.filter(location_id=location_id)
    
    current_stock = current_stock_query.aggregate(total=Sum('quantity'))['total'] or 0
    
    # Calculate opening stock (current stock - net movement)
    opening_stock = current_stock - net_movement
    
    # Movement by type breakdown
    movement_breakdown = {
        'purchases': sum(m['quantity'] for m in movements if m['type'] == 'purchase'),
        'sales': sum(m['quantity'] for m in movements if m['type'] == 'sale'),
        'transfers_in': sum(m['quantity'] for m in movements if m['type'] == 'transfer_in'),
        'transfers_out': sum(m['quantity'] for m in movements if m['type'] == 'transfer_out'),
        'adjustments': sum(m['quantity'] for m in movements if m['type'] == 'adjustment'),
    }
    
    context = {
        'product': product,
        'movements': movements,
        'total_in': total_in,
        'total_out': total_out,
        'net_movement': net_movement,
        'total_in_value': total_in_value,
        'total_out_value': total_out_value,
        'net_value_movement': net_value_movement,
        'current_stock': current_stock,
        'opening_stock': opening_stock,
        'movement_breakdown': movement_breakdown,
        
        # Filter options
        'locations': user_locations,
        'transaction_types': [
            ('all', 'All Transactions'),
            ('purchase', 'Purchases'),
            ('sale', 'Sales'),
            ('transfer_in', 'Transfers In'),
            ('transfer_out', 'Transfers Out'),
            ('adjustment', 'Adjustments'),
        ],
        
        # Current filter values
        'date_from': date_from,
        'date_to': date_to,
        'location_id': location_id,
        'transaction_type': transaction_type,
    }
    
    return render(request, 'inventory/reports/product_movement.html', context)


@login_required
def product_movement_export(request, product_id):
    """Export product movement report to CSV"""
    product = get_object_or_404(Product, id=product_id)
    
    # Get the same data as the report view
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{product.sku}_movement_report_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Product Movement Report',
        f'Product: {product.name}',
        f'SKU: {product.sku}',
        f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}',
    ])
    writer.writerow([])
    
    # Write summary
    writer.writerow(['SUMMARY'])
    writer.writerow(['Opening Stock', 'Total In', 'Total Out', 'Net Movement', 'Current Stock'])
    
    # You would need to calculate these values similar to the report view
    # For simplicity, I'm showing the structure
    writer.writerow(['0', '0', '0', '0', '0'])  # Placeholder
    
    writer.writerow([])
    writer.writerow(['DETAILED MOVEMENT HISTORY'])
    writer.writerow([
        'Date', 'Type', 'Reference', 'Description', 'Quantity', 'In/Out',
        'Unit Price', 'Total Value', 'Location'
    ])
    
    # Get movements data (simplified version)
    movements = []  # You would populate this similar to the report view
    
    for movement in movements:
        writer.writerow([
            movement['date'].strftime('%Y-%m-%d %H:%M'),
            movement['type'].replace('_', ' ').title(),
            movement['reference'],
            movement['description'],
            movement['quantity'],
            movement['in_out'].upper(),
            f"{movement['unit_price']:.2f}",
            f"{movement['total_value']:.2f}",
            movement['location'].name,
        ])
    
    return response

# =======================
# PURCHASE REPORTS
# =======================

@login_required
def purchase_summary_report(request):
    """Purchase summary report with supplier analysis"""
    purchases = Purchase.objects.all()
    purchases = filter_queryset_by_user_locations(purchases, request.user)
    purchases = purchases.select_related('location').prefetch_related('items__product')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    supplier_filter = request.GET.get('supplier', '')
    location_id = request.GET.get('location', '')
    group_by = request.GET.get('group_by', 'daily')  # daily, weekly, monthly, supplier
    
    # Apply filters
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    if supplier_filter:
        purchases = purchases.filter(supplier_name__icontains=supplier_filter)
    if location_id:
        try:
            location = Location.objects.get(id=location_id)
            if can_user_access_location(request.user, location):
                purchases = purchases.filter(location_id=location_id)
        except Location.DoesNotExist:
            pass
    
    # Calculate summary statistics
    total_spent = purchases.aggregate(total=Sum('total_amount'))['total'] or 0
    total_quantity = sum(purchase.get_total_quantity() for purchase in purchases)
    total_purchases = purchases.count()
    
    # Group data based on selection
    if group_by == 'daily':
        grouped_data = purchases.extra({
            'date': "DATE(purchase_date)"
        }).values('date').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            quantity=Sum('items__quantity')
        ).order_by('date')
    elif group_by == 'weekly':
        grouped_data = purchases.extra({
            'week': "EXTRACT(WEEK FROM purchase_date)",
            'year': "EXTRACT(YEAR FROM purchase_date)"
        }).values('year', 'week').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            quantity=Sum('items__quantity')
        ).order_by('year', 'week')
    elif group_by == 'monthly':
        grouped_data = purchases.extra({
            'month': "EXTRACT(MONTH FROM purchase_date)",
            'year': "EXTRACT(YEAR FROM purchase_date)"
        }).values('year', 'month').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            quantity=Sum('items__quantity')
        ).order_by('year', 'month')
    elif group_by == 'supplier':
        grouped_data = purchases.values('supplier_name').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            quantity=Sum('items__quantity'),
            avg_order_value=Avg('total_amount')
        ).order_by('-amount')
    else:
        grouped_data = []
    
    # Supplier performance analysis
    supplier_performance = purchases.values('supplier_name').annotate(
        total_spent=Sum('total_amount'),
        order_count=Count('id'),
        total_quantity=Sum('items__quantity'),
        avg_order_value=Avg('total_amount'),
        last_order_date=Max('purchase_date')
    ).order_by('-total_spent')
    
    # Top purchased products
    top_products = PurchaseItem.objects.filter(purchase__in=purchases).values(
        'product__name', 'product__sku'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_cost=Sum(F('quantity') * F('unit_price')),
        avg_unit_price=Avg('unit_price')
    ).order_by('-total_quantity')[:10]
    
    # Monthly trend (last 12 months)
    twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
    monthly_trend = purchases.filter(purchase_date__gte=twelve_months_ago).extra({
        'month': "EXTRACT(MONTH FROM purchase_date)",
        'year': "EXTRACT(YEAR FROM purchase_date)"
    }).values('year', 'month').annotate(
        amount=Sum('total_amount'),
        purchase_count=Count('id')
    ).order_by('year', 'month')
    
    context = {
        'purchases': purchases,
        'grouped_data': grouped_data,
        'supplier_performance': supplier_performance,
        'top_products': top_products,
        'monthly_trend': monthly_trend,
        'total_spent': total_spent,
        'total_quantity': total_quantity,
        'total_purchases': total_purchases,
        'avg_order_value': total_spent / total_purchases if total_purchases > 0 else 0,
        
        # Filter options
        'locations': get_user_locations(request.user),
        'unique_suppliers': list(set(p.supplier_name for p in purchases if p.supplier_name)),
        
        # Current filter values
        'date_from': date_from,
        'date_to': date_to,
        'supplier_filter': supplier_filter,
        'location_id': location_id,
        'group_by': group_by,
    }
    return render(request, 'inventory/reports/purchase_summary.html', context)


@login_required
def supplier_analysis_report(request):
    """Detailed supplier performance analysis"""
    purchases = Purchase.objects.all()
    purchases = filter_queryset_by_user_locations(purchases, request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    min_orders = request.GET.get('min_orders', 1)
    
    try:
        min_orders = int(min_orders)
    except ValueError:
        min_orders = 1
    
    # Apply date filters
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    
    # Supplier performance analysis
    supplier_data = {}
    
    for purchase in purchases.select_related('location').prefetch_related('items__product'):
        supplier = purchase.supplier_name
        if not supplier:
            continue
            
        if supplier not in supplier_data:
            supplier_data[supplier] = {
                'total_spent': 0,
                'order_count': 0,
                'total_quantity': 0,
                'products_purchased': set(),
                'locations': set(),
                'first_order_date': purchase.purchase_date,
                'last_order_date': purchase.purchase_date,
                'purchases': []
            }
        
        data = supplier_data[supplier]
        data['total_spent'] += float(purchase.total_amount)
        data['order_count'] += 1
        data['total_quantity'] += purchase.get_total_quantity()
        
        # Add products and locations
        for item in purchase.items.all():
            data['products_purchased'].add(item.product.name)
        data['locations'].add(purchase.location.name)
        
        # Update dates
        if purchase.purchase_date < data['first_order_date']:
            data['first_order_date'] = purchase.purchase_date
        if purchase.purchase_date > data['last_order_date']:
            data['last_order_date'] = purchase.purchase_date
        
        # Store purchase details
        data['purchases'].append(purchase)
    
    # Convert to list and apply minimum orders filter
    supplier_list = []
    for supplier_name, data in supplier_data.items():
        if data['order_count'] >= min_orders:
            data['supplier_name'] = supplier_name
            data['avg_order_value'] = data['total_spent'] / data['order_count']
            data['products_count'] = len(data['products_purchased'])
            data['locations_count'] = len(data['locations'])
            
            # Calculate supplier lifetime (in days)
            lifetime_days = (data['last_order_date'] - data['first_order_date']).days
            data['lifetime_days'] = max(lifetime_days, 1)
            data['avg_days_between_orders'] = data['lifetime_days'] / data['order_count'] if data['order_count'] > 1 else 0
            
            supplier_list.append(data)
    
    # Sort options
    sort_by = request.GET.get('sort_by', 'total_spent')
    sort_options = {
        'total_spent': lambda x: x['total_spent'],
        'order_count': lambda x: x['order_count'],
        'avg_order_value': lambda x: x['avg_order_value'],
        'products_count': lambda x: x['products_count'],
        'last_order_date': lambda x: x['last_order_date'],
    }
    
    if sort_by in sort_options:
        supplier_list.sort(key=sort_options[sort_by], reverse=True)
    
    # Supplier segmentation
    segments = {
        'strategic': [],  # Top 20% by spending
        'preferred': [],  # Middle 60%
        'occasional': [],  # Bottom 20%
    }
    
    if supplier_list:
        sorted_by_spent = sorted(supplier_list, key=lambda x: x['total_spent'], reverse=True)
        total_suppliers = len(sorted_by_spent)
        
        strategic_count = max(1, int(total_suppliers * 0.2))
        preferred_count = int(total_suppliers * 0.6)
        
        segments['strategic'] = sorted_by_spent[:strategic_count]
        segments['preferred'] = sorted_by_spent[strategic_count:strategic_count + preferred_count]
        segments['occasional'] = sorted_by_spent[strategic_count + preferred_count:]
    
    # Summary statistics
    total_spent = sum(supplier['total_spent'] for supplier in supplier_list)
    total_orders = sum(supplier['order_count'] for supplier in supplier_list)
    total_suppliers = len(supplier_list)
    avg_spent_per_supplier = total_spent / total_suppliers if total_suppliers > 0 else 0
    
    context = {
        'supplier_analysis': supplier_list,
        'supplier_segments': segments,
        'total_spent': total_spent,
        'total_orders': total_orders,
        'total_suppliers': total_suppliers,
        'avg_spent_per_supplier': avg_spent_per_supplier,
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'min_orders': min_orders,
        'sort_by': sort_by,
    }
    return render(request, 'inventory/reports/supplier_analysis.html', context)


@login_required
def purchase_product_analysis_report(request):
    """Product-wise purchase analysis"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    category_id = request.GET.get('category', '')
    supplier_filter = request.GET.get('supplier', '')
    location_id = request.GET.get('location', '')
    min_quantity = request.GET.get('min_quantity', 0)
    
    try:
        min_quantity = int(min_quantity)
    except ValueError:
        min_quantity = 0
    
    # Get purchase items with filters
    purchase_items = PurchaseItem.objects.filter(
        purchase__location__in=user_locations
    ).select_related('product', 'product__category', 'purchase', 'purchase__location')
    
    # Apply filters
    if date_from:
        purchase_items = purchase_items.filter(purchase__purchase_date__date__gte=date_from)
    if date_to:
        purchase_items = purchase_items.filter(purchase__purchase_date__date__lte=date_to)
    if category_id:
        purchase_items = purchase_items.filter(product__category_id=category_id)
    if supplier_filter:
        purchase_items = purchase_items.filter(purchase__supplier_name__icontains=supplier_filter)
    if location_id:
        purchase_items = purchase_items.filter(purchase__location_id=location_id)
    
    # Product-wise aggregation
    product_analysis = purchase_items.values(
        'product__id', 'product__name', 'product__sku', 'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_cost=Sum(F('quantity') * F('unit_price')),
        avg_unit_price=Avg('unit_price'),
        min_unit_price=Min('unit_price'),
        max_unit_price=Max('unit_price'),
        purchase_count=Count('purchase', distinct=True),
        supplier_count=Count('purchase__supplier_name', distinct=True)
    ).order_by('-total_cost')
    
    # Apply minimum quantity filter
    product_analysis = [p for p in product_analysis if p['total_quantity'] >= min_quantity]
    
    # Calculate price variance and trends
    for product in product_analysis:
        product_id = product['product__id']
        
        # Get price history
        price_history = PurchaseItem.objects.filter(
            product_id=product_id,
            purchase__location__in=user_locations
        )
        
        if date_from:
            price_history = price_history.filter(purchase__purchase_date__date__gte=date_from)
        if date_to:
            price_history = price_history.filter(purchase__purchase_date__date__lte=date_to)
        
        price_history = price_history.order_by('purchase__purchase_date')
        
        # Calculate price stability
        prices = list(price_history.values_list('unit_price', flat=True))
        if len(prices) > 1:
            min_price = min(prices)
            max_price = max(prices)
            price_variance = ((max_price - min_price) / min_price * 100) if min_price > 0 else 0
            product['price_variance'] = price_variance
            product['price_stability'] = 'High' if price_variance < 10 else 'Medium' if price_variance < 25 else 'Low'
        else:
            product['price_variance'] = 0
            product['price_stability'] = 'Unknown'
        
        # Latest purchase info
        latest_purchase = price_history.last()
        if latest_purchase:
            product['latest_purchase_date'] = latest_purchase.purchase.purchase_date
            product['latest_unit_price'] = latest_purchase.unit_price
        else:
            product['latest_purchase_date'] = None
            product['latest_unit_price'] = 0
    
    # Summary statistics
    total_products = len(product_analysis)
    total_quantity = sum(p['total_quantity'] for p in product_analysis)
    total_cost = sum(p['total_cost'] for p in product_analysis)
    avg_cost_per_product = total_cost / total_products if total_products > 0 else 0
    
    # Identify products with significant price changes
    high_variance_products = [p for p in product_analysis if p.get('price_variance', 0) > 20]
    
    context = {
        'product_analysis': product_analysis,
        'high_variance_products': high_variance_products,
        'total_products': total_products,
        'total_quantity': total_quantity,
        'total_cost': total_cost,
        'avg_cost_per_product': avg_cost_per_product,
        
        # Filter options
        'categories': Category.objects.all(),
        'locations': user_locations,
        'unique_suppliers': list(set(
            item.purchase.supplier_name for item in purchase_items 
            if item.purchase.supplier_name
        )),
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'category_id': category_id,
        'supplier_filter': supplier_filter,
        'location_id': location_id,
        'min_quantity': min_quantity,
    }
    return render(request, 'inventory/reports/purchase_product_analysis.html', context)


@login_required
def purchase_trend_analysis_report(request):
    """Purchase trend analysis over time"""
    purchases = Purchase.objects.all()
    purchases = filter_queryset_by_user_locations(purchases, request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    period = request.GET.get('period', 'monthly')  # daily, weekly, monthly, quarterly
    
    # Set default date range (last 12 months if not specified)
    if not date_from:
        date_from = (timezone.now() - timezone.timedelta(days=365)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = timezone.now().strftime('%Y-%m-%d')
    
    # Apply date filters
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    
    # Generate trend data based on period
    if period == 'daily':
        trend_data = purchases.extra({
            'period': "DATE(purchase_date)"
        }).values('period').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            avg_order_value=Avg('total_amount')
        ).order_by('period')
    elif period == 'weekly':
        trend_data = purchases.extra({
            'period': "CONCAT(EXTRACT(YEAR FROM purchase_date), '-W', LPAD(EXTRACT(WEEK FROM purchase_date), 2, '0'))"
        }).values('period').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            avg_order_value=Avg('total_amount')
        ).order_by('period')
    elif period == 'monthly':
        trend_data = purchases.extra({
            'period': "CONCAT(EXTRACT(YEAR FROM purchase_date), '-', LPAD(EXTRACT(MONTH FROM purchase_date), 2, '0'))"
        }).values('period').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            avg_order_value=Avg('total_amount')
        ).order_by('period')
    elif period == 'quarterly':
        trend_data = purchases.extra({
            'period': "CONCAT(EXTRACT(YEAR FROM purchase_date), '-Q', EXTRACT(QUARTER FROM purchase_date))"
        }).values('period').annotate(
            amount=Sum('total_amount'),
            purchase_count=Count('id'),
            avg_order_value=Avg('total_amount')
        ).order_by('period')
    else:
        trend_data = []
    
    # Calculate moving averages (3-period)
    trend_list = list(trend_data)
    for i in range(2, len(trend_list)):
        prev_periods = trend_list[i-2:i+1]
        moving_avg = sum(item['amount'] for item in prev_periods) / 3
        trend_list[i]['moving_average'] = moving_avg
    
    # YoY growth calculation (for monthly data)
    if period == 'monthly':
        monthly_data = {}
        for item in trend_list:
            year_month = item['period']
            year = year_month.split('-')[0]
            month = year_month.split('-')[1]
            
            if year not in monthly_data:
                monthly_data[year] = {}
            monthly_data[year][month] = item['amount']
        
        # Calculate YoY growth
        years = sorted(monthly_data.keys())
        if len(years) >= 2:
            current_year = years[-1]
            previous_year = years[-2]
            
            for month in monthly_data[current_year]:
                if month in monthly_data[previous_year]:
                    current_amount = monthly_data[current_year][month]
                    previous_amount = monthly_data[previous_year][month]
                    growth = ((current_amount - previous_amount) / previous_amount * 100) if previous_amount > 0 else 0
                    
                    # Add growth to trend data
                    for item in trend_list:
                        if item['period'] == f"{current_year}-{month}":
                            item['yoy_growth'] = growth
                            break
    
    # Seasonal analysis (if we have multiple years of data)
    seasonal_analysis = {}
    if period == 'monthly' and len(trend_list) >= 12:
        monthly_totals = {}
        for item in trend_list:
            month = item['period'].split('-')[1]
            if month not in monthly_totals:
                monthly_totals[month] = []
            monthly_totals[month].append(item['amount'])
        
        for month, amounts in monthly_totals.items():
            if len(amounts) > 1:
                seasonal_analysis[month] = {
                    'avg_amount': sum(amounts) / len(amounts),
                    'min_amount': min(amounts),
                    'max_amount': max(amounts),
                    'trend': 'increasing' if amounts[-1] > amounts[0] else 'decreasing'
                }
    
    context = {
        'trend_data': trend_list,
        'seasonal_analysis': seasonal_analysis,
        'total_amount': sum(item['amount'] for item in trend_list),
        'total_purchases': sum(item['purchase_count'] for item in trend_list),
        'avg_order_value': sum(item['amount'] for item in trend_list) / len(trend_list) if trend_list else 0,
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'period': period,
    }
    return render(request, 'inventory/reports/purchase_trend_analysis.html', context)


@login_required
def export_purchase_report(request, report_type):
    """Export purchase reports to CSV"""
    response = HttpResponse(content_type='text/csv')
    filename = f'purchase_{report_type}_{timezone.now().strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    if report_type == 'summary':
        writer.writerow(['Purchase Summary Report', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Period', 'Total Amount', 'Purchase Count', 'Total Quantity'])
        # Add actual data here based on your summary report
        writer.writerow(['All Time', '0', '0', '0'])  # Placeholder
    
    elif report_type == 'supplier_analysis':
        writer.writerow(['Supplier Analysis Report', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Supplier', 'Total Spent', 'Order Count', 'Avg Order Value', 'Products Purchased'])
        # Add actual data here
    
    elif report_type == 'product_analysis':
        writer.writerow(['Product Purchase Analysis', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Product', 'SKU', 'Total Quantity', 'Total Cost', 'Avg Unit Price', 'Purchase Count'])
        # Add actual data here
    
    return response
# =======================
# TRANSFER REPORTS
# =======================

@login_required
def transfer_summary_report(request):
    """Transfer summary report with location analysis"""
    transfer_batches = TransferBatch.objects.all()
    transfer_batches = filter_queryset_by_user_locations(transfer_batches, request.user, 'from_location')
    transfer_batches = transfer_batches.select_related('from_location', 'to_location', 'created_by').prefetch_related('items__product')
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    from_location_id = request.GET.get('from_location', '')
    to_location_id = request.GET.get('to_location', '')
    status_filter = request.GET.get('status', '')
    group_by = request.GET.get('group_by', 'daily')  # daily, weekly, monthly, location
    
    # Apply filters
    if date_from:
        transfer_batches = transfer_batches.filter(created_at__date__gte=date_from)
    if date_to:
        transfer_batches = transfer_batches.filter(created_at__date__lte=date_to)
    if from_location_id:
        transfer_batches = transfer_batches.filter(from_location_id=from_location_id)
    if to_location_id:
        transfer_batches = transfer_batches.filter(to_location_id=to_location_id)
    if status_filter:
        transfer_batches = transfer_batches.filter(status=status_filter)
    
    # Calculate summary statistics
    total_transfers = transfer_batches.count()
    total_items = sum(batch.items.count() for batch in transfer_batches)
    total_quantity = sum(item.quantity for batch in transfer_batches for item in batch.items.all())
    
    # Get completed transfers for value calculation
    completed_transfers = transfer_batches.filter(status='confirmed')
    total_transfer_value = 0
    for batch in completed_transfers:
        for item in batch.items.all():
            total_transfer_value += item.quantity * item.product.cost_price
    
    # Group data based on selection
    if group_by == 'daily':
        grouped_data = transfer_batches.extra({
            'date': "DATE(created_at)"
        }).values('date').annotate(
            transfer_count=Count('id'),
            item_count=Count('items'),
            total_quantity=Sum('items__quantity')
        ).order_by('date')
    elif group_by == 'weekly':
        grouped_data = transfer_batches.extra({
            'week': "EXTRACT(WEEK FROM created_at)",
            'year': "EXTRACT(YEAR FROM created_at)"
        }).values('year', 'week').annotate(
            transfer_count=Count('id'),
            item_count=Count('items'),
            total_quantity=Sum('items__quantity')
        ).order_by('year', 'week')
    elif group_by == 'monthly':
        grouped_data = transfer_batches.extra({
            'month': "EXTRACT(MONTH FROM created_at)",
            'year': "EXTRACT(YEAR FROM created_at)"
        }).values('year', 'month').annotate(
            transfer_count=Count('id'),
            item_count=Count('items'),
            total_quantity=Sum('items__quantity')
        ).order_by('year', 'month')
    elif group_by == 'location_pair':
        grouped_data = transfer_batches.values('from_location__name', 'to_location__name').annotate(
            transfer_count=Count('id'),
            item_count=Count('items'),
            total_quantity=Sum('items__quantity'),
            completed_count=Count('id', filter=Q(status='confirmed')),
            pending_count=Count('id', filter=Q(status='pending'))
        ).order_by('-transfer_count')
    else:
        grouped_data = []
    
    # Location-wise analysis
    location_analysis = {}
    for batch in transfer_batches:
        # As source location
        from_loc = batch.from_location.name
        if from_loc not in location_analysis:
            location_analysis[from_loc] = {
                'outgoing_transfers': 0,
                'outgoing_quantity': 0,
                'outgoing_items': 0,
                'incoming_transfers': 0,
                'incoming_quantity': 0,
                'incoming_items': 0
            }
        
        location_analysis[from_loc]['outgoing_transfers'] += 1
        location_analysis[from_loc]['outgoing_items'] += batch.items.count()
        location_analysis[from_loc]['outgoing_quantity'] += sum(item.quantity for item in batch.items.all())
        
        # As destination location
        to_loc = batch.to_location.name
        if to_loc not in location_analysis:
            location_analysis[to_loc] = {
                'outgoing_transfers': 0,
                'outgoing_quantity': 0,
                'outgoing_items': 0,
                'incoming_transfers': 0,
                'incoming_quantity': 0,
                'incoming_items': 0
            }
        
        location_analysis[to_loc]['incoming_transfers'] += 1
        location_analysis[to_loc]['incoming_items'] += batch.items.count()
        location_analysis[to_loc]['incoming_quantity'] += sum(item.quantity for item in batch.items.all())
    
    # Convert to list for template
    location_analysis_list = [
        {'location': loc, **data} for loc, data in location_analysis.items()
    ]
    location_analysis_list.sort(key=lambda x: x['outgoing_quantity'] + x['incoming_quantity'], reverse=True)
    
    # Top transferred products
    top_products = StockTransfer.objects.filter(
        batch__in=transfer_batches
    ).values(
        'product__name', 'product__sku'
    ).annotate(
        total_quantity=Sum('quantity'),
        transfer_count=Count('batch', distinct=True),
        location_count=Count('batch__from_location', distinct=True)
    ).order_by('-total_quantity')[:10]
    
    # Status breakdown
    status_breakdown = transfer_batches.values('status').annotate(
        count=Count('id'),
        total_quantity=Sum('items__quantity')
    ).order_by('status')
    
    context = {
        'transfer_batches': transfer_batches,
        'grouped_data': grouped_data,
        'location_analysis': location_analysis_list,
        'top_products': top_products,
        'status_breakdown': status_breakdown,
        'total_transfers': total_transfers,
        'total_items': total_items,
        'total_quantity': total_quantity,
        'total_transfer_value': total_transfer_value,
        'avg_items_per_transfer': total_items / total_transfers if total_transfers > 0 else 0,
        
        # Filter options
        'locations': get_user_locations(request.user),
        'status_choices': TransferBatch.STATUS_CHOICES,
        
        # Current filter values
        'date_from': date_from,
        'date_to': date_to,
        'from_location_id': from_location_id,
        'to_location_id': to_location_id,
        'status_filter': status_filter,
        'group_by': group_by,
    }
    return render(request, 'inventory/reports/transfer_summary.html', context)


@login_required
def transfer_location_analysis_report(request):
    """Detailed location-wise transfer analysis"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_id = request.GET.get('location', '')
    analysis_type = request.GET.get('analysis_type', 'both')  # incoming, outgoing, both
    
    # Get all transfers involving user's locations
    transfers_as_source = TransferBatch.objects.filter(from_location__in=user_locations)
    transfers_as_destination = TransferBatch.objects.filter(to_location__in=user_locations)
    
    # Apply date filters
    if date_from:
        transfers_as_source = transfers_as_source.filter(created_at__date__gte=date_from)
        transfers_as_destination = transfers_as_destination.filter(created_at__date__gte=date_from)
    if date_to:
        transfers_as_source = transfers_as_source.filter(created_at__date__lte=date_to)
        transfers_as_destination = transfers_as_destination.filter(created_at__date__lte=date_to)
    
    # Apply location filter
    if location_id:
        transfers_as_source = transfers_as_source.filter(from_location_id=location_id)
        transfers_as_destination = transfers_as_destination.filter(to_location_id=location_id)
        selected_location = get_object_or_404(Location, id=location_id)
    else:
        selected_location = None
    
    # Build location analysis
    location_data = {}
    
    # Analyze outgoing transfers
    if analysis_type in ['both', 'outgoing']:
        for batch in transfers_as_source.select_related('from_location', 'to_location').prefetch_related('items__product'):
            from_loc = batch.from_location
            to_loc = batch.to_location
            
            if from_loc.id not in location_data:
                location_data[from_loc.id] = {
                    'location': from_loc,
                    'outgoing': {
                        'transfer_count': 0,
                        'total_quantity': 0,
                        'total_value': 0,
                        'destinations': {},
                        'products': {}
                    },
                    'incoming': {
                        'transfer_count': 0,
                        'total_quantity': 0,
                        'total_value': 0,
                        'sources': {},
                        'products': {}
                    }
                }
            
            # Outgoing data
            loc_data = location_data[from_loc.id]['outgoing']
            loc_data['transfer_count'] += 1
            loc_data['total_quantity'] += sum(item.quantity for item in batch.items.all())
            loc_data['total_value'] += sum(item.quantity * item.product.cost_price for item in batch.items.all())
            
            # Track destinations
            if to_loc.name not in loc_data['destinations']:
                loc_data['destinations'][to_loc.name] = 0
            loc_data['destinations'][to_loc.name] += 1
            
            # Track products
            for item in batch.items.all():
                product_key = f"{item.product.name} ({item.product.sku})"
                if product_key not in loc_data['products']:
                    loc_data['products'][product_key] = 0
                loc_data['products'][product_key] += item.quantity
    
    # Analyze incoming transfers
    if analysis_type in ['both', 'incoming']:
        for batch in transfers_as_destination.select_related('from_location', 'to_location').prefetch_related('items__product'):
            from_loc = batch.from_location
            to_loc = batch.to_location
            
            if to_loc.id not in location_data:
                location_data[to_loc.id] = {
                    'location': to_loc,
                    'outgoing': {
                        'transfer_count': 0,
                        'total_quantity': 0,
                        'total_value': 0,
                        'destinations': {},
                        'products': {}
                    },
                    'incoming': {
                        'transfer_count': 0,
                        'total_quantity': 0,
                        'total_value': 0,
                        'sources': {},
                        'products': {}
                    }
                }
            
            # Incoming data
            loc_data = location_data[to_loc.id]['incoming']
            loc_data['transfer_count'] += 1
            loc_data['total_quantity'] += sum(item.quantity for item in batch.items.all())
            loc_data['total_value'] += sum(item.quantity * item.product.cost_price for item in batch.items.all())
            
            # Track sources
            if from_loc.name not in loc_data['sources']:
                loc_data['sources'][from_loc.name] = 0
            loc_data['sources'][from_loc.name] += 1
            
            # Track products
            for item in batch.items.all():
                product_key = f"{item.product.name} ({item.product.sku})"
                if product_key not in loc_data['products']:
                    loc_data['products'][product_key] = 0
                loc_data['products'][product_key] += item.quantity
    
    # Convert to list and calculate net flow
    location_analysis = []
    for loc_id, data in location_data.items():
        net_quantity = data['incoming']['total_quantity'] - data['outgoing']['total_quantity']
        net_value = data['incoming']['total_value'] - data['outgoing']['total_value']
        
        location_analysis.append({
            **data,
            'net_quantity': net_quantity,
            'net_value': net_value,
            'flow_direction': 'balanced' if abs(net_quantity) < 10 else 'incoming' if net_quantity > 0 else 'outgoing'
        })
    
    # Sort based on analysis type
    if analysis_type == 'outgoing':
        location_analysis.sort(key=lambda x: x['outgoing']['total_quantity'], reverse=True)
    elif analysis_type == 'incoming':
        location_analysis.sort(key=lambda x: x['incoming']['total_quantity'], reverse=True)
    else:
        location_analysis.sort(key=lambda x: abs(x['net_quantity']), reverse=True)
    
    # Summary statistics
    total_outgoing = sum(item['outgoing']['total_quantity'] for item in location_analysis)
    total_incoming = sum(item['incoming']['total_quantity'] for item in location_analysis)
    net_flow = total_incoming - total_outgoing
    
    context = {
        'location_analysis': location_analysis,
        'selected_location': selected_location,
        'total_outgoing': total_outgoing,
        'total_incoming': total_incoming,
        'net_flow': net_flow,
        'total_transfers': sum(item['outgoing']['transfer_count'] + item['incoming']['transfer_count'] for item in location_analysis) // 2,  # Divide by 2 to avoid double counting
        
        # Filter options
        'locations': user_locations,
        'analysis_types': [
            ('both', 'Both Incoming & Outgoing'),
            ('incoming', 'Incoming Only'),
            ('outgoing', 'Outgoing Only'),
        ],
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'location_id': location_id,
        'analysis_type': analysis_type,
    }
    return render(request, 'inventory/reports/transfer_location_analysis.html', context)


@login_required
def transfer_product_analysis_report(request):
    """Product-wise transfer analysis"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    category_id = request.GET.get('category', '')
    from_location_id = request.GET.get('from_location', '')
    to_location_id = request.GET.get('to_location', '')
    min_quantity = request.GET.get('min_quantity', 0)
    
    try:
        min_quantity = int(min_quantity)
    except ValueError:
        min_quantity = 0
    
    # Get transfer items with filters
    transfer_items = StockTransfer.objects.filter(
        batch__from_location__in=user_locations,
        status='completed'
    ).select_related('product', 'product__category', 'batch__from_location', 'batch__to_location')
    
    # Apply filters
    if date_from:
        transfer_items = transfer_items.filter(transfer_date__date__gte=date_from)
    if date_to:
        transfer_items = transfer_items.filter(transfer_date__date__lte=date_to)
    if category_id:
        transfer_items = transfer_items.filter(product__category_id=category_id)
    if from_location_id:
        transfer_items = transfer_items.filter(batch__from_location_id=from_location_id)
    if to_location_id:
        transfer_items = transfer_items.filter(batch__to_location_id=to_location_id)
    
    # Product-wise aggregation
    product_analysis = transfer_items.values(
        'product__id', 'product__name', 'product__sku', 'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        transfer_count=Count('batch', distinct=True),
        from_location_count=Count('batch__from_location', distinct=True),
        to_location_count=Count('batch__to_location', distinct=True),
        total_value=Sum(F('quantity') * F('product__cost_price'))
    ).order_by('-total_quantity')
    
    # Apply minimum quantity filter
    product_analysis = [p for p in product_analysis if p['total_quantity'] >= min_quantity]
    
    # Get detailed transfer routes for each product
    for product in product_analysis:
        product_id = product['product__id']
        
        # Get transfer routes (from -> to)
        routes = transfer_items.filter(product_id=product_id).values(
            'batch__from_location__name', 'batch__to_location__name'
        ).annotate(
            quantity=Sum('quantity'),
            transfer_count=Count('id')
        ).order_by('-quantity')
        
        product['top_routes'] = list(routes[:5])  # Top 5 routes
        
        # Get transfer frequency
        monthly_transfers = transfer_items.filter(
            product_id=product_id
        ).extra({
            'month': "EXTRACT(MONTH FROM transfer_date)",
            'year': "EXTRACT(YEAR FROM transfer_date)"
        }).values('year', 'month').annotate(
            monthly_quantity=Sum('quantity')
        ).order_by('year', 'month')
        
        product['transfer_frequency'] = 'High' if len(monthly_transfers) > 6 else 'Medium' if len(monthly_transfers) > 2 else 'Low'
        
        # Calculate transfer velocity (quantity per transfer)
        product['avg_quantity_per_transfer'] = product['total_quantity'] / product['transfer_count'] if product['transfer_count'] > 0 else 0
    
    # Identify most transferred products
    most_transferred = sorted(product_analysis, key=lambda x: x['total_quantity'], reverse=True)[:10]
    
    # Identify products with highest transfer value
    highest_value = sorted(product_analysis, key=lambda x: x['total_value'], reverse=True)[:10]
    
    # Summary statistics
    total_products = len(product_analysis)
    total_quantity = sum(p['total_quantity'] for p in product_analysis)
    total_value = sum(p['total_value'] for p in product_analysis)
    total_transfers = sum(p['transfer_count'] for p in product_analysis)
    
    context = {
        'product_analysis': product_analysis,
        'most_transferred': most_transferred,
        'highest_value': highest_value,
        'total_products': total_products,
        'total_quantity': total_quantity,
        'total_value': total_value,
        'total_transfers': total_transfers,
        'avg_quantity_per_product': total_quantity / total_products if total_products > 0 else 0,
        
        # Filter options
        'categories': Category.objects.all(),
        'locations': user_locations,
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
        'category_id': category_id,
        'from_location_id': from_location_id,
        'to_location_id': to_location_id,
        'min_quantity': min_quantity,
    }
    return render(request, 'inventory/reports/transfer_product_analysis.html', context)


@login_required
def transfer_efficiency_report(request):
    """Transfer efficiency and performance analysis"""
    user_locations = get_user_locations(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Set default date range (last 90 days if not specified)
    if not date_from:
        date_from = (timezone.now() - timezone.timedelta(days=90)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = timezone.now().strftime('%Y-%m-%d')
    
    # Get completed transfers
    completed_transfers = TransferBatch.objects.filter(
        from_location__in=user_locations,
        status='confirmed',
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).select_related('from_location', 'to_location').prefetch_related('items__product')
    
    # Get pending transfers for comparison
    pending_transfers = TransferBatch.objects.filter(
        from_location__in=user_locations,
        status='pending',
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    )
    
    # Efficiency metrics calculation
    efficiency_data = []
    
    for batch in completed_transfers:
        # Calculate transfer time (from creation to confirmation)
        if batch.confirmed_at:
            transfer_time_hours = (batch.confirmed_at - batch.created_at).total_seconds() / 3600
        else:
            transfer_time_hours = 24  # Default assumption
        
        # Calculate efficiency metrics
        total_items = batch.items.count()
        total_quantity = sum(item.quantity for item in batch.items.all())
        total_value = sum(item.quantity * item.product.cost_price for item in batch.items.all())
        
        # Efficiency score (lower time and higher quantity = better)
        time_efficiency = max(0, 100 - (transfer_time_hours / 24 * 10))  # 24 hours = 90% efficiency
        quantity_efficiency = min(100, total_quantity / 10 * 100)  # 10 items = 100% efficiency
        overall_efficiency = (time_efficiency + quantity_efficiency) / 2
        
        efficiency_data.append({
            'batch': batch,
            'transfer_time_hours': transfer_time_hours,
            'total_items': total_items,
            'total_quantity': total_quantity,
            'total_value': total_value,
            'time_efficiency': time_efficiency,
            'quantity_efficiency': quantity_efficiency,
            'overall_efficiency': overall_efficiency,
            'efficiency_grade': 'A' if overall_efficiency >= 90 else 'B' if overall_efficiency >= 75 else 'C' if overall_efficiency >= 60 else 'D'
        })
    
    # Sort by efficiency
    efficiency_data.sort(key=lambda x: x['overall_efficiency'], reverse=True)
    
    # Location-wise efficiency
    location_efficiency = {}
    for data in efficiency_data:
        from_loc = data['batch'].from_location.name
        to_loc = data['batch'].to_location.name
        route_key = f"{from_loc} → {to_loc}"
        
        if route_key not in location_efficiency:
            location_efficiency[route_key] = {
                'transfer_count': 0,
                'avg_transfer_time': 0,
                'avg_efficiency': 0,
                'total_quantity': 0,
                'total_value': 0
            }
        
        loc_data = location_efficiency[route_key]
        loc_data['transfer_count'] += 1
        loc_data['avg_transfer_time'] += data['transfer_time_hours']
        loc_data['avg_efficiency'] += data['overall_efficiency']
        loc_data['total_quantity'] += data['total_quantity']
        loc_data['total_value'] += data['total_value']
    
    # Calculate averages
    for route_data in location_efficiency.values():
        if route_data['transfer_count'] > 0:
            route_data['avg_transfer_time'] /= route_data['transfer_count']
            route_data['avg_efficiency'] /= route_data['transfer_count']
    
    # Convert to list and sort
    location_efficiency_list = [
        {'route': route, **data} for route, data in location_efficiency.items()
    ]
    location_efficiency_list.sort(key=lambda x: x['avg_efficiency'], reverse=True)
    
    # Performance trends (monthly)
    monthly_trends = completed_transfers.extra({
        'month': "EXTRACT(MONTH FROM created_at)",
        'year': "EXTRACT(YEAR FROM created_at)"
    }).values('year', 'month').annotate(
        transfer_count=Count('id'),
        avg_transfer_time=Avg(
            (F('confirmed_at') - F('created_at')) / 3600.0
        ),
        total_quantity=Sum('items__quantity'),
        avg_efficiency=Avg(
            (100 - ( (F('confirmed_at') - F('created_at')) / 86400.0 * 10 )) +  # Time component
            (Least(100, F('items__quantity') * 10.0))  # Quantity component
        ) / 2
    ).order_by('year', 'month')
    
    # Summary statistics
    total_completed = completed_transfers.count()
    total_pending = pending_transfers.count()
    avg_transfer_time = sum(data['transfer_time_hours'] for data in efficiency_data) / len(efficiency_data) if efficiency_data else 0
    avg_efficiency = sum(data['overall_efficiency'] for data in efficiency_data) / len(efficiency_data) if efficiency_data else 0
    
    context = {
        'efficiency_data': efficiency_data,
        'location_efficiency': location_efficiency_list,
        'monthly_trends': monthly_trends,
        'total_completed': total_completed,
        'total_pending': total_pending,
        'completion_rate': total_completed / (total_completed + total_pending) * 100 if (total_completed + total_pending) > 0 else 0,
        'avg_transfer_time': avg_transfer_time,
        'avg_efficiency': avg_efficiency,
        
        # Filter values
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'inventory/reports/transfer_efficiency.html', context)


@login_required
def export_transfer_report(request, report_type):
    """Export transfer reports to CSV"""
    response = HttpResponse(content_type='text/csv')
    filename = f'transfer_{report_type}_{timezone.now().strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    if report_type == 'summary':
        writer.writerow(['Transfer Summary Report', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Period', 'Transfer Count', 'Item Count', 'Total Quantity'])
        # Add actual data here
        writer.writerow(['All Time', '0', '0', '0'])  # Placeholder
    
    elif report_type == 'location_analysis':
        writer.writerow(['Transfer Location Analysis', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Location', 'Outgoing Transfers', 'Incoming Transfers', 'Net Quantity'])
        # Add actual data here
    
    elif report_type == 'product_analysis':
        writer.writerow(['Product Transfer Analysis', f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        writer.writerow(['Product', 'SKU', 'Total Quantity', 'Transfer Count', 'Total Value'])
        # Add actual data here
    
    return response

@login_required
def supplier_analysis_report(request):
    """Supplier performance and analysis report"""
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    location_filter = request.GET.get('location', '')
    min_orders = int(request.GET.get('min_orders', 1))
    
    # Get purchases with filters
    purchases = Purchase.objects.all()
    
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)
    if location_filter:
        purchases = purchases.filter(location_id=location_filter)
    
    # Calculate supplier performance
    supplier_performance = {}
    
    for purchase in purchases.select_related('location').prefetch_related('items'):
        supplier_name = purchase.supplier_name
        if not supplier_name:
            continue
            
        if supplier_name not in supplier_performance:
            supplier_performance[supplier_name] = {
                'name': supplier_name,
                'total_spent': 0,
                'order_count': 0,
                'last_order_date': purchase.purchase_date,
                'locations': set(),
                'total_items': 0
            }
        
        supplier_data = supplier_performance[supplier_name]
        supplier_data['total_spent'] += float(purchase.total_amount)
        supplier_data['order_count'] += 1
        supplier_data['total_items'] += purchase.get_total_quantity()
        supplier_data['locations'].add(purchase.location.name)
        
        if purchase.purchase_date > supplier_data['last_order_date']:
            supplier_data['last_order_date'] = purchase.purchase_date
    
    # Calculate averages and prepare data
    supplier_list = []
    for supplier_name, data in supplier_performance.items():
        if data['order_count'] >= min_orders:
            data['avg_order_value'] = data['total_spent'] / data['order_count']
            data['locations_list'] = list(data['locations'])
            supplier_list.append(data)
    
    # Sort by total spent (highest first)
    supplier_list.sort(key=lambda x: x['total_spent'], reverse=True)
    
    # Get top products
    top_products = PurchaseItem.objects.filter(
        purchase__in=purchases
    ).values(
        'product__name', 'product__sku', 'purchase__supplier_name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_cost=Sum(F('quantity') * F('unit_price')),
        avg_unit_price=Avg('unit_price')
    ).order_by('-total_quantity')[:20]
    
    # Calculate summary statistics
    total_suppliers = len(supplier_list)
    total_spent = sum(supplier['total_spent'] for supplier in supplier_list)
    total_orders = sum(supplier['order_count'] for supplier in supplier_list)
    avg_order_value = total_spent / total_orders if total_orders > 0 else 0
    
    context = {
        'supplier_performance': supplier_list,
        'top_products': top_products,
        'total_suppliers': total_suppliers,
        'total_spent': total_spent,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'locations': get_user_locations(request.user),
        'date_from': date_from,
        'date_to': date_to,
        'location_filter': location_filter,
        'min_orders': min_orders,
    }
    
    return render(request, 'inventory/reports/supplier_analysis.html', context)