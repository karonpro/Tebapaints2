from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
import csv
from .forms import ExpenseForm

from .models import (
    Transaction, Customer, Payment,
    Expense, ExpenseName,ExpenseName
)
from .forms import (
    TransactionForm, CustomerForm,
    PaymentForm, ExpenseForm
)

# ---------------- Transactions ----------------

from datetime import datetime
from django.db.models import Q, Sum
from django.utils import timezone
from django.shortcuts import render
from transactions.models import Transaction
from core.models import Location

def transaction_list(request):
    q = request.GET.get('q', '').strip()
    location = request.GET.get('location', '')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Base queryset
    qs = Transaction.objects.all().order_by('-created_at')

    # --- Filters ---
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            qs = qs.filter(date__gte=start)
        except ValueError:
            pass

    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            qs = qs.filter(date__lte=end)
        except ValueError:
            pass

    if not start_date and not end_date:
        qs = qs.filter(date=timezone.localdate())

    if location:
        qs = qs.filter(location_id=location)

    if q:
        qs = qs.filter(Q(notes__icontains=q))

    # --- Totals ---
    totals_raw = qs.aggregate(
        paid=Sum('paid'),
        customer_balance=Sum('customer_balance'),
        wholesale=Sum('wholesale'),
        debt=Sum('debt'),
        cash=Sum('cash'),
        accounts=Sum('accounts'),
        expenses=Sum('expenses'),
        opening_balance=Sum('opening_balance'),
    )

    # Replace None with 0
    for k, v in totals_raw.items():
        totals_raw[k] = v or 0

    totals = {
        "sales": totals_raw['paid'] + totals_raw['customer_balance'] + totals_raw['wholesale'],
        "cashout": totals_raw['debt'] + totals_raw['cash'] + totals_raw['accounts'] + totals_raw['expenses'],
    }
    totals["difference"] = totals["sales"] - totals["cashout"]
    totals["less_excess"] = totals["difference"] - totals_raw['opening_balance']

    # --- Separate Less and Excess ---
    total_less = 0
    total_excess = 0
    for row in qs:
        row_diff = (row.paid + row.customer_balance + row.wholesale) - \
                   (row.debt + row.cash + row.accounts + row.expenses)
        less_excess = row_diff - (row.opening_balance or 0)
        if less_excess < 0:
            total_less += abs(less_excess)
        elif less_excess > 0:
            total_excess += less_excess

    # --- Locations for filter dropdown ---
    locations = Location.objects.all()

    return render(request, 'transactions/transaction_list.html', {
        'rows': qs,
        'totals': totals,
        'locations': locations,
        'selected_location': location,
        'start_date': start_date,
        'end_date': end_date,
        'less_value': total_less,
        'excess_value': total_excess,
    })



def transaction_add(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.user = None
            t.save()
            return redirect('transactions:list')
    else:
        form = TransactionForm()
    return render(request, 'transactions/transaction_form.html', {'form': form, 'create': True})


def transaction_edit(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect('transactions:list')
    else:
        form = TransactionForm(instance=obj)
    return render(request, 'transactions/transaction_form.html', {'form': form, 'create': False, 'obj': obj})


def transaction_delete(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('transactions:list')
    return render(request, 'transactions/transaction_confirm_delete.html', {'obj': obj})


def transaction_detail(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    return render(request, 'transactions/transaction_detail.html', {'transaction': transaction})


# ---------------- Customers ----------------

def customer_add(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('transactions:customers')
    else:
        form = CustomerForm()
    return render(request, 'transactions/customer_form.html', {'form': form})


def customer_edit(request, pk):
    obj = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect('transactions:customers')
    else:
        form = CustomerForm(instance=obj)
    return render(request, 'transactions/customer_form.html', {'form': form, 'obj': obj})


def customer_delete(request, pk):
    obj = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('transactions:customers')
    return render(request, 'transactions/customer_confirm_delete.html', {'obj': obj})

from django.shortcuts import render
from django.db.models import Sum, Max
from transactions.models import Customer
from inventory.models import Sale
from datetime import datetime

def customers_list(request):
    customers = Customer.objects.all()

    # --- Filters ---
    name = request.GET.get('name')
    phone = request.GET.get('phone')
    tin = request.GET.get('tin')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if name:
        customers = customers.filter(name__icontains=name)
    if phone:
        customers = customers.filter(phone__icontains=phone)
    if tin:
        customers = customers.filter(tin__icontains=tin)

    # Annotate with latest sale date
    customers = customers.annotate(last_sale_date=Max('sale__date'))

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            customers = customers.filter(last_sale_date__gte=start)
        except:
            pass
    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d")
            customers = customers.filter(last_sale_date__lte=end)
        except:
            pass

    # --- Totals after filtering ---
    total_sales_amount = 0
    total_paid_amount = 0
    total_balance = 0

    for customer in customers:
        sales = Sale.objects.filter(customer=customer)
        customer.total_sales = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        customer.total_paid = sales.aggregate(total=Sum('paid_amount'))['total'] or 0
       

        total_sales_amount += customer.total_sales
        total_paid_amount += customer.total_paid
        total_balance += customer.balance

    context = {
        'customers': customers,
        'total_sales_amount': total_sales_amount,
        'total_paid_amount': total_paid_amount,
        'total_balance': total_balance,
        'request': request,
    }
    return render(request, 'transactions/customers_list.html', context)


def customer_info(request, pk):
    try:
        c = Customer.objects.get(pk=pk)
        return JsonResponse({
            'ok': True, 
            'balance': str(c.balance),  # This uses the property getter - OK
            'supply': str(c.supply), 
            'name': c.name
        })
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False}, status=404)

# Add to transactions/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import F
from .models import Customer
from inventory.models import Sale, Payment

@login_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(
        Customer.objects.prefetch_related('sale_set__payments', 'sale_set__items'),
        id=customer_id
    )
    
    # Get all sales for this customer
    sales = Sale.objects.filter(customer=customer).select_related(
        'location'
    ).prefetch_related('items__product', 'payments').order_by('-date')
    
    # Get recent payments
    recent_payments = Payment.objects.filter(
        sale__customer=customer
    ).select_related('sale', 'received_by').order_by('-payment_date')[:10]
    
    # Calculate statistics
    total_sales_amount = sum(sale.total_amount for sale in sales)
    total_paid_amount = sum(sale.paid_amount for sale in sales)
    total_balance = customer.total_balance
    overdue_balance = customer.overdue_balance
    
    overdue_sales = sales.filter(
        due_date__lt=timezone.now().date(),
        paid_amount__lt=F('total_amount')
    )
    
    
    context = {
        'customer': customer,
        'sales': sales,
        'recent_payments': recent_payments,
        'overdue_sales': overdue_sales,
        'total_sales_amount': total_sales_amount,
        'total_paid_amount': total_paid_amount,
        'total_balance': total_balance,
        'overdue_balance': overdue_balance,
        'total_sales_count': sales.count(),
    }
    
    return render(request, 'transactions/customer_detail.html', context)

# ---------------- Payments ----------------  


@login_required
def payment_add(request):
    """Simple payment add view - redirects to customer payment"""
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            # You'll need to handle customer selection here
            # For now, redirect to customers list
            messages.info(request, "Please select a customer first to record payment")
            return redirect('transactions:customers_list')
    else:
        form = PaymentForm()
    return render(request, 'transactions/payment_form_simple.html', {'form': form})

@login_required
def receive_payment(request, customer_id):
    """Record payment with option to pay specific sale or general debt"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    # Debug: Print customer info
    print(f"Customer: {customer.name}, ID: {customer.id}")
    
    # Get unpaid sales for this customer
    try:
        from inventory.models import Sale
        # Try different ways to get unpaid sales
        all_sales = Sale.objects.filter(customer=customer)
        print(f"Total sales found: {all_sales.count()}")
        
        # Method 1: Using balance_due property
        unpaid_sales = [sale for sale in all_sales if getattr(sale, 'balance_due', 0) > 0]
        print(f"Unpaid sales (method 1): {len(unpaid_sales)}")
        
        # Method 2: Using paid_amount vs total_amount
        if not unpaid_sales:
            unpaid_sales = [sale for sale in all_sales if getattr(sale, 'paid_amount', 0) < getattr(sale, 'total_amount', 0)]
            print(f"Unpaid sales (method 2): {len(unpaid_sales)}")
            
        # Method 3: Direct database query
        if not unpaid_sales:
            unpaid_sales = Sale.objects.filter(
                customer=customer
            ).exclude(
                paid_amount=models.F('total_amount')
            )
            print(f"Unpaid sales (method 3): {unpaid_sales.count()}")
            
    except Exception as e:
        print(f"Error fetching sales: {e}")
        unpaid_sales = []
    
    # Debug: Print sales info
    for sale in unpaid_sales:
        print(f"Sale: {sale.document_number}, Total: {getattr(sale, 'total_amount', 'N/A')}, Paid: {getattr(sale, 'paid_amount', 'N/A')}, Balance: {getattr(sale, 'balance_due', 'N/A')}")
    
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            # ... rest of the POST handling code ...
            pass
    else:
        form = PaymentForm(initial={'date': timezone.now().date()})
    
    context = {
        "customer": customer,
        "form": form,
        "unpaid_sales": unpaid_sales,
        "title": "Receive Payment",
    }
    return render(request, "transactions/payment_form.html", context)
# ---------------- Expenses ----------------

from django.shortcuts import render, redirect
from django.db.models import Sum
from .forms import ExpenseForm
from .models import Expense, ExpenseName

def expense_add(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.added_by = request.user
            expense.save()
            return redirect('transactions:expenses')  # ✅ fixed name
    else:
        form = ExpenseForm()
    return render(request, 'transactions/expense_form.html', {'form': form})

def expenses_list(request):
    qs = Expense.objects.all().order_by('-date')
    name_filter = request.GET.get('name', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if name_filter:
        qs = qs.filter(name__icontains=name_filter)
    if start_date and end_date:
        qs = qs.filter(date__range=[start_date, end_date])

    total = qs.aggregate(total_amount=Sum('amount'))['total_amount'] or 0

    return render(request, 'transactions/expenses_list.html', {
        'expenses': qs,
        'expense_names': ExpenseName.objects.all(),
        'total': total,
        'name_filter': name_filter,
        'start_date': start_date,
        'end_date': end_date,
    })

from django.shortcuts import render, redirect, get_object_or_404
from .forms import ExpenseForm
from .models import Expense, ExpenseName

# --- Add Expense (already present) ---
# expense_add view from previous message

# --- Edit Expense ---
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            return redirect('transactions:expenses_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'transactions/expense_form.html', {'form': form, 'edit': True, 'expense': expense})

# --- Delete Expense ---
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        return redirect('transactions:expenses_list')
    return render(request, 'transactions/expense_confirm_delete.html', {'expense': expense})


# ---------------- Reports ----------------

def daily_report(request):
    query = request.GET.get('q', '')
    if query:
        transactions = Transaction.objects.filter(accounts__icontains=query).order_by('-id')
    else:
        transactions = Transaction.objects.all().order_by('-id')

    paginator = Paginator(transactions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'transactions/report_daily.html', {
        'transactions': page_obj,
        'query': query,
    })


def daily_export(request):
    date = request.GET.get('date') or timezone.localdate().isoformat()
    qs = Transaction.objects.filter(date=date)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="report_{date}.csv"'
    writer = csv.writer(response)
    writer.writerow(['id', 'date', 'location', 'total_sales', 'total_cashout', 'difference', 'less_excess'])
    for t in qs:
        writer.writerow([t.id, t.date, t.location.name if t.location else '',
                         t.total_sales, t.total_cashout, t.difference, t.less_excess])
    return response


def report_home(request):
    return render(request, 'transactions/report_home.html')


def customer_report(request):
    customers = Customer.objects.all()
    payments = Payment.objects.all()
    start = request.GET.get('start')
    end = request.GET.get('end')
    if start and end:
        payments = payments.filter(date__range=[parse_date(start), parse_date(end)])
    totals = payments.aggregate(total_paid=Sum('amount'))
    return render(request, 'transactions/customer_report.html', {
        'customers': customers,
        'payments': payments,
        'totals': totals
    })


def expense_report(request):
    expenses = Expense.objects.all()
    start = request.GET.get('start')
    end = request.GET.get('end')
    if start and end:
        expenses = expenses.filter(date__range=[parse_date(start), parse_date(end)])
    total = expenses.aggregate(total_expenses=Sum('amount'))
    return render(request, 'transactions/expense_report.html', {
        'expenses': expenses,
        'total': total
    })


def transaction_report(request):
    transactions = Transaction.objects.all()
    start = request.GET.get('start')
    end = request.GET.get('end')
    if start and end:
        transactions = transactions.filter(date__range=[parse_date(start), parse_date(end)])

    location = request.GET.get('location')
    try:
        from core.models import Location
        locations = Location.objects.all()
    except:
        locations = []
    if location:
        transactions = transactions.filter(location_id=location)

    totals = {
        'opening_balance': transactions.aggregate(Sum('opening_balance'))['opening_balance__sum'] or 0,
        'customer_balance': transactions.aggregate(Sum('customer_balance'))['customer_balance__sum'] or 0,
        'paid': transactions.aggregate(Sum('paid'))['paid__sum'] or 0,
        'wholesale': transactions.aggregate(Sum('wholesale'))['wholesale__sum'] or 0,
        'debt': transactions.aggregate(Sum('debt'))['debt__sum'] or 0,
        'accounts': transactions.aggregate(Sum('accounts'))['accounts__sum'] or 0,
        'expenses': transactions.aggregate(Sum('expenses'))['expenses__sum'] or 0,
        'cash': transactions.aggregate(Sum('cash'))['cash__sum'] or 0,
        'difference': sum([t.difference for t in transactions]),
        'less_excess': sum([t.less_excess for t in transactions]),
    }

    return render(request, 'transactions/transaction_report.html', {
        'transactions': transactions,
        'totals': totals,
        'locations': locations,
        'selected_location': location,
        'start': start,
        'end': end,
    })

# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Customer, SupplyHistory  # ✅ correct
from .forms import SupplyForm


@login_required
def add_supply(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)

    if request.method == "POST":
        form = SupplyForm(request.POST)
        if form.is_valid():
            supply = form.save(commit=False)
            supply.customer = customer
            supply.save()

           
            messages.success(request, f"Supply of {supply.amount} added for {customer.name}.")
            return redirect("transactions:customer_detail", pk=customer.id)
    else:
        form = SupplyForm()

    context = {
        "customer": customer,
        "form": form,
    }
    return render(request, "transactions/add_supply.html", context)


import csv
from django.http import HttpResponse
from .models import Customer

def export_customers_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customers.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Phone', 'Email', 'TIN', 'Supply', 'Balance'])

    for customer in Customer.objects.all():
        writer.writerow([customer.name, customer.phone, customer.email, customer.tin, customer.supply, customer.balance])

    return response

from django.shortcuts import render, get_object_or_404
from .models import Transaction

def view_transaction(request, id):
    """
    Display a single transaction details, similar layout to the transaction form.
    """
    transaction = get_object_or_404(Transaction, pk=id)

    # Compute totals
    total_sales = (transaction.paid or 0) + (transaction.customer_balance or 0) + (transaction.wholesale or 0)
    total_cashout = (transaction.debt or 0) + (transaction.cash or 0) + (transaction.accounts or 0) + (transaction.expenses or 0)
    difference = total_sales - total_cashout
    less_excess = difference - (transaction.opening_balance or 0)

    if less_excess > 0:
        less_excess_status = f"Less {less_excess:.2f}"
        less_excess_class = "bg-warning text-dark"
    elif less_excess < 0:
        less_excess_status = f"Excess {abs(less_excess):.2f}"
        less_excess_class = "bg-danger text-white"
    else:
        less_excess_status = "Balanced"
        less_excess_class = "bg-success text-white"

    context = {
        'transaction': transaction,
        'total_sales': total_sales,
        'total_cashout': total_cashout,
        'difference': difference,
        'less_excess_status': less_excess_status,
        'less_excess_class': less_excess_class,
    }

    return render(request, 'transactions/view_transaction.html', context)














# ---------------- Home ----------------
# transactions/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum
from .models import Customer
from inventory.models import Sale, Payment

# transactions/views.py - Update the home view


# transactions/views.py - Add this API view
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime
from inventory.models import Sale, SaleItem

# transactions/views.py - Enhanced home view with inventory stats
@login_required
def home(request):
    """Dashboard home"""
    try:
        today = timezone.localdate()
        
        # Get today's transactions
        today_transactions = Transaction.objects.filter(date=today)
        today_transactions_count = today_transactions.count()
        
        # Calculate today's sales and cashout from transactions
        today_sales_totals = today_transactions.aggregate(
            total_paid=Sum('paid'),
            total_customer_balance=Sum('customer_balance'),
            total_wholesale=Sum('wholesale'),
            total_debt=Sum('debt'),
            total_cash=Sum('cash'),
            total_accounts=Sum('accounts'),
            total_expenses=Sum('expenses')
        )
        
        today_sales = (today_sales_totals.get('total_paid') or 0) + \
                     (today_sales_totals.get('total_customer_balance') or 0) + \
                     (today_sales_totals.get('total_wholesale') or 0)
        
        today_cashout = (today_sales_totals.get('total_debt') or 0) + \
                       (today_sales_totals.get('total_cash') or 0) + \
                       (today_sales_totals.get('total_accounts') or 0) + \
                       (today_sales_totals.get('total_expenses') or 0)
        
        # Get other statistics
        total_customers = Customer.objects.count()
        recent_customers = Customer.objects.all().order_by('-created_at')[:5]
        
        # Get inventory statistics
        try:
            from inventory.models import Product, ProductStock, PurchaseOrder, SaleOrder
            total_products = Product.objects.count()
            low_stock_products = Product.objects.annotate(
                total_stock=Sum('stocks__quantity')
            ).filter(total_stock__lt=10).count()
            
            # Get pending orders counts
            pending_purchase_orders = PurchaseOrder.objects.filter(status='ordered').count()
            pending_sale_orders = SaleOrder.objects.filter(status='draft').count()
            
        except Exception as e:
            total_products = 0
            low_stock_products = 0
            pending_purchase_orders = 0
            pending_sale_orders = 0
        
        context = {
            'today_transactions_count': today_transactions_count,
            'total_customers': total_customers,
            'recent_customers': recent_customers,
            'today_sales': today_sales,
            'today_cashout': today_cashout,
            'total_products': total_products,
            'low_stock_products': low_stock_products,
            'pending_purchase_orders': pending_purchase_orders,
            'pending_sale_orders': pending_sale_orders,
        }
        return render(request, "transactions/home.html", context)
        
    except Exception as e:
        print(f"Error in home view: {e}")
        # Fallback context
        context = {
            'today_transactions_count': 0,
            'total_customers': 0,
            'recent_customers': [],
            'today_sales': 0,
            'today_cashout': 0,
            'total_products': 0,
            'low_stock_products': 0,
            'pending_purchase_orders': 0,
            'pending_sale_orders': 0,
        }
        return render(request, "transactions/home.html", context)

@login_required
def customer_details_api(request, customer_id):
    try:
        from transactions.models import Customer
        customer = Customer.objects.get(id=customer_id)
        
        # Get all sales for this customer
        sales = Sale.objects.filter(customer=customer).select_related('location').order_by('-date')
        
        # Calculate totals
        total_sales = sales.count()
        total_amount = sum(sale.total_amount for sale in sales)
        total_paid = sum(sale.paid_amount for sale in sales)
        total_balance = total_amount - total_paid
        
        # Get recent sales (last 5)
        recent_sales = sales[:5]
        
        # Get overdue sales
        overdue_sales = []
        for sale in sales:
            if sale.due_date and sale.balance_due > 0:
                days_overdue = (timezone.now().date() - sale.due_date).days
                if days_overdue > 0:
                    overdue_sales.append({
                        'id': sale.id,
                        'document_number': sale.document_number,
                        'due_date': sale.due_date.isoformat(),
                        'balance': float(sale.balance_due),
                        'days_overdue': days_overdue
                    })
        
        # Prepare response data
        data = {
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'email': customer.email,
                'address': customer.address,
            },
            'total_sales': total_sales,
            'total_amount': float(total_amount),
            'total_paid': float(total_paid),
            'total_balance': float(total_balance),
            'recent_sales': [
                {
                    'id': sale.id,
                    'document_number': sale.document_number,
                    'date': sale.date.isoformat(),
                    'total_amount': float(sale.total_amount),
                    'paid_amount': float(sale.paid_amount),
                    'balance': float(sale.balance_due),
                    'status': sale.document_status,
                }
                for sale in recent_sales
            ],
            'overdue_sales': overdue_sales,
        }
        
        return JsonResponse(data)
        
    except Customer.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    # transactions/views.py
from django.shortcuts import render, get_object_or_404
from .models import Customer
from inventory.models import Sale

def customer_ledger(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    
    # Get all sales for this customer that are sent, paid, or overdue
    sales = Sale.objects.filter(customer=customer).order_by('-date')
    
    # Calculate total balance
    total_balance = sum(sale.balance_due for sale in sales)
    
    context = {
        'customer': customer,
        'sales': sales,
        'total_balance': total_balance,
    }
    return render(request, 'transactions/customer_ledger.html', context)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

@login_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(
        Customer.objects.prefetch_related('sale_set__payments', 'sale_set__items'),
        id=customer_id
    )
    
    # Get all sales for this customer
    try:
        from inventory.models import Sale
        sales = Sale.objects.filter(customer=customer).select_related(
            'location'
        ).prefetch_related('items__product', 'payments').order_by('-date')
    except Exception as e:
        sales = []
    
    # Get recent payments
    try:
        from inventory.models import Payment
        recent_payments = Payment.objects.filter(
            sale__customer=customer
        ).select_related('sale', 'received_by').order_by('-payment_date')[:10]
    except Exception as e:
        recent_payments = []
    
    # Calculate statistics
    total_sales_amount = customer.total_sales_amount
    total_paid_amount = customer.total_paid_amount
    total_balance = customer.total_balance
    overdue_balance = customer.overdue_balance
    
    context = {
        'customer': customer,
        'sales': sales,
        'recent_payments': recent_payments,
        'total_sales_amount': total_sales_amount,
        'total_paid_amount': total_paid_amount,
        'total_balance': total_balance,
        'overdue_balance': overdue_balance,
        'total_sales_count': customer.total_sales_count,
    }
    
    return render(request, 'transactions/customer_detail.html', context)

# Add this to transactions/views.py (as an alias for customer_details_api)
@login_required
def api_customer_details(request, customer_id):
    """Alias for customer_details_api - same functionality"""
    return customer_details_api(request, customer_id)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Customer, BalanceAdjustment
from .forms import BalanceAdjustmentForm

@login_required
def add_customer_balance(request, customer_id):
    """Add credit to customer balance without affecting stock"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == "POST":
        form = BalanceAdjustmentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data['notes']
            reference = form.cleaned_data.get('reference', '')
            
            # Update customer balance
            customer.update_balance(
                amount=amount,
                adjustment_type='credit',
                notes=notes,
                reference=reference,
                user=request.user
            )
            
            messages.success(
                request, 
                f"Successfully added ${amount:.2f} credit to {customer.name}'s account."
            )
            return redirect("transactions:customer_detail", customer_id=customer.id)
    else:
        form = BalanceAdjustmentForm()
    
    context = {
        "customer": customer,
        "form": form,
        "title": "Add Customer Credit",
        "adjustment_type": "credit",
    }
    return render(request, "transactions/balance_adjustment.html", context)

@login_required
def deduct_customer_balance(request, customer_id):
    """Deduct from customer balance"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == "POST":
        form = BalanceAdjustmentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data['notes']
            reference = form.cleaned_data.get('reference', '')
            
            # Check if customer has sufficient balance
            if amount > customer.balance:
                messages.error(
                    request, 
                    f"Cannot deduct ${amount:.2f}. Customer only has ${customer.balance:.2f} available."
                )
            else:
                # Update customer balance
                customer.update_balance(
                    amount=amount,
                    adjustment_type='debit',
                    notes=notes,
                    reference=reference,
                    user=request.user
                )
                
                messages.success(
                    request, 
                    f"Successfully deducted ${amount:.2f} from {customer.name}'s account."
                )
                return redirect("transactions:customer_detail", customer_id=customer.id)
    else:
        form = BalanceAdjustmentForm()
    
    context = {
        "customer": customer,
        "form": form,
        "title": "Deduct Customer Balance",
        "adjustment_type": "debit",
    }
    return render(request, "transactions/balance_adjustment.html", context)

@login_required
def customer_balance_history(request, customer_id):
    """View customer's balance adjustment history"""
    customer = get_object_or_404(Customer, id=customer_id)
    adjustments = BalanceAdjustment.objects.filter(customer=customer).select_related('created_by').order_by('-created_at')
    
    # Calculate totals
    total_credit = adjustments.filter(
        adjustment_type__in=['credit', 'supply', 'payment']
    ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    total_debit = adjustments.filter(adjustment_type='debit').aggregate(total=models.Sum('amount'))['total'] or 0
    net_adjustment = total_credit - total_debit
    
    context = {
        'customer': customer,
        'adjustments': adjustments,
        'total_credit': total_credit,
        'total_debit': total_debit,
        'net_adjustment': net_adjustment,
    }
    return render(request, 'transactions/balance_history.html', context)

@login_required
def quick_balance_adjustment(request, customer_id):
    """Quick balance adjustment via AJAX"""
    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        customer = get_object_or_404(Customer, id=customer_id)
        
        adjustment_type = request.POST.get('type')
        amount = request.POST.get('amount')
        notes = request.POST.get('notes', '')
        
        try:
            amount = float(amount)
            if amount <= 0:
                return JsonResponse({'success': False, 'error': 'Amount must be positive'})
            
            if adjustment_type == 'debit' and amount > customer.balance:
                return JsonResponse({
                    'success': False, 
                    'error': f'Insufficient balance. Available: ${customer.balance:.2f}'
                })
            
            # Update balance
            customer.update_balance(
                amount=amount,
                adjustment_type=adjustment_type,
                notes=notes,
                user=request.user
            )
            
            return JsonResponse({
                'success': True,
                'new_balance': float(customer.balance),
                'message': f'Balance updated successfully. New balance: ${customer.balance:.2f}'
            })
            
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid amount'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import models
from .models import Customer, DebtTransaction
from .forms import DebtForm, PaymentForm

@login_required
def add_customer_debt(request, customer_id):
    """Record when you supply goods to customer on credit - they owe YOU money"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == "POST":
        form = DebtForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data['notes']
            reference = form.cleaned_data.get('reference', '')
            
            # INCREASE customer debt (they owe you more money)
            customer.balance += amount
            customer.save()
            
            # Record the debt transaction
            DebtTransaction.objects.create(
                customer=customer,
                amount=amount,
                transaction_type='supply',
                notes=f"Goods supply: {notes}",
                reference=reference,
                created_by=request.user
            )
            
            messages.success(
                request, 
                f"Recorded supply debt of UGX {amount:,.0f} for {customer.name}. Total debt: UGX {customer.balance:,.0f}"
            )
            return redirect("transactions:customer_detail", customer_id=customer.id)
    else:
        form = DebtForm()
    
    context = {
        "customer": customer,
        "form": form,
        "title": "Record Supply Debt",
    }
    return render(request, "transactions/debt_form.html", context)

@login_required
def receive_payment(request, customer_id):
    """Record when customer pays towards their debt - they owe you LESS money"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data['notes']
            reference = form.cleaned_data.get('reference', '')
            
            # Check if payment exceeds debt
            if amount > customer.balance:
                messages.error(
                    request, 
                    f"Cannot receive UGX {amount:,.0f}. Customer only owes UGX {customer.balance:,.0f}"
                )
            else:
                # DECREASE customer debt (they owe you less)
                customer.balance -= amount
                customer.save()
                
                # Record the payment transaction
                DebtTransaction.objects.create(
                    customer=customer,
                    amount=amount,
                    transaction_type='payment',
                    notes=f"Payment received: {notes}",
                    reference=reference,
                    created_by=request.user
                )
                
                messages.success(
                    request, 
                    f"Received payment of UGX {amount:,.0f} from {customer.name}. Remaining debt: UGX {customer.balance:,.0f}"
                )
                return redirect("transactions:customer_detail", customer_id=customer.id)
    else:
        form = PaymentForm()
    
    context = {
        "customer": customer,
        "form": form,
        "title": "Receive Payment",
    }
    return render(request, "transactions/payment_form.html", context)

@login_required
def customer_debt_history(request, customer_id):
    """View customer's debt transaction history"""
    customer = get_object_or_404(Customer, id=customer_id)
    transactions = DebtTransaction.objects.filter(customer=customer).select_related('created_by').order_by('-created_at')
    
    # Calculate totals
    total_supply = transactions.filter(transaction_type='supply').aggregate(total=models.Sum('amount'))['total'] or 0
    total_payments = transactions.filter(transaction_type='payment').aggregate(total=models.Sum('amount'))['total'] or 0
    net_debt = total_supply - total_payments
    
    context = {
        'customer': customer,
        'transactions': transactions,
        'total_supply': total_supply,
        'total_payments': total_payments,
        'net_debt': net_debt,
    }
    return render(request, 'transactions/debt_history.html', context)

@login_required
def quick_supply_debt(request, customer_id):
    """Quick supply debt recording via AJAX"""
    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        customer = get_object_or_404(Customer, id=customer_id)
        
        amount = request.POST.get('amount')
        notes = request.POST.get('notes', 'Quick supply')
        
        try:
            amount = float(amount)
            if amount <= 0:
                return JsonResponse({'success': False, 'error': 'Amount must be positive'})
            
            # Increase customer debt
            customer.balance += amount
            customer.save()
            
            # Record transaction
            DebtTransaction.objects.create(
                customer=customer,
                amount=amount,
                transaction_type='supply',
                notes=notes,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'new_balance': float(customer.balance),
                'message': f'Supply recorded successfully. Total debt: UGX {customer.balance:,.0f}'
            })
            
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid amount'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Keep this for actual credit scenarios (when customer pays in advance)
@login_required  
def add_customer_credit(request, customer_id):
    """ONLY use this when customer pays in advance (rare scenario)"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == "POST":
        form = BalanceAdjustmentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data['notes']
            
            # This should DECREASE balance (customer owes less because they paid in advance)
            customer.balance -= amount
            if customer.balance < 0:
                customer.balance = 0
            customer.save()
            
            messages.success(
                request, 
                f"Added UGX {amount:,.0f} credit to {customer.name}. They can use this for future purchases."
            )
            return redirect("transactions:customer_detail", customer_id=customer.id)
    else:
        form = BalanceAdjustmentForm()
    
    context = {
        "customer": customer,
        "form": form,
        "title": "Add Customer Credit (Advance Payment)",
    }
    return render(request, "transactions/credit_form.html", context)

    # transactions/views.py - ADD THIS VIEW


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import models
import logging
from decimal import Decimal, InvalidOperation
from .models import Customer, DebtTransaction
from .forms import DebtForm, PaymentForm

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def receive_unified_payment(request, customer_id):
    """
    Unified payment view that handles both general debt and specific invoice payments
    with proper error handling, validation, and business logic.
    """
    customer = get_object_or_404(Customer, id=customer_id)
    
    # Get unpaid sales and customer debt data
    unpaid_sales, total_sales_balance = _get_customer_unpaid_sales(customer)
    total_customer_debt = customer.balance
    
    # Handle pre-selected sale from URL
    preselected_sale_id = request.GET.get('sale_id')
    initial_data = _get_initial_payment_data(preselected_sale_id)
    
    if request.method == "POST":
        return _handle_payment_post(request, customer, unpaid_sales, total_customer_debt)
    
    # GET request - show payment form
    context = {
        "customer": customer,
        "unpaid_sales": unpaid_sales,
        "total_sales_balance": total_sales_balance,
        "total_customer_debt": total_customer_debt,
       "default_date": timezone.now().strftime(r'%Y-%m-%d\T%H:%M'),
        "initial_payment_type": initial_data['payment_type'],
        "initial_sale_id": initial_data['sale_id'],
        "preselected_sale_id": preselected_sale_id,
    }
    return render(request, "transactions/unified_payment_form.html", context)


def _get_customer_unpaid_sales(customer):
    """
    Get all unpaid sales for a customer with their balances.
    Returns tuple: (unpaid_sales_list, total_balance)
    """
    unpaid_sales = []
    total_balance = Decimal('0')
    
    try:
        from inventory.models import Sale
        
        # Get sales with unpaid balance
        all_sales = Sale.objects.filter(customer=customer).select_related('location').order_by('-date')
        
        for sale in all_sales:
            balance_due = _calculate_sale_balance(sale)
            
            if balance_due > 0:
                sale.calculated_balance = balance_due
                unpaid_sales.append(sale)
                total_balance += balance_due
                
    except Exception as e:
        logger.error(f"Error fetching unpaid sales for customer {customer.id}: {e}")
    
    return unpaid_sales, total_balance


def _calculate_sale_balance(sale):
    """
    Calculate the balance due for a sale using multiple fallback methods.
    """
    # Method 1: Use balance_due property if available
    if hasattr(sale, 'balance_due') and sale.balance_due is not None:
        return Decimal(str(sale.balance_due))
    
    # Method 2: Calculate from total_amount and paid_amount
    if (hasattr(sale, 'total_amount') and hasattr(sale, 'paid_amount') and 
        sale.total_amount is not None):
        paid = Decimal(str(sale.paid_amount)) if sale.paid_amount else Decimal('0')
        total = Decimal(str(sale.total_amount))
        return max(total - paid, Decimal('0'))
    
    # Method 3: Default to total_amount if paid_amount not available
    if hasattr(sale, 'total_amount') and sale.total_amount is not None:
        return Decimal(str(sale.total_amount))
    
    return Decimal('0')


def _get_initial_payment_data(preselected_sale_id):
    """
    Determine initial form data based on preselected sale.
    """
    if preselected_sale_id:
        return {'payment_type': 'sale', 'sale_id': preselected_sale_id}
    return {'payment_type': 'debt', 'sale_id': ''}


def _handle_payment_post(request, customer, unpaid_sales, total_customer_debt):
    """
    Process payment form submission.
    """
    form_data = _extract_payment_form_data(request.POST)
    
    # Validate basic form data
    validation_error = _validate_payment_form_data(form_data)
    if validation_error:
        messages.error(request, validation_error)
        return _render_payment_form_with_error(request, customer, unpaid_sales, total_customer_debt, form_data)
    
    try:
        # Process payment based on type
        if form_data['payment_type'] == 'sale' and form_data['sale_id']:
            return _process_invoice_payment(request, customer, form_data)
        else:
            return _process_manual_debt_payment(request, customer, form_data)
            
    except ValueError as e:
        messages.error(request, f"Invalid amount or date format: {str(e)}")
        logger.warning(f"ValueError in payment processing: {e}")
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        logger.error(f"Exception in payment processing: {e}", exc_info=True)
    
    return _render_payment_form_with_error(request, customer, unpaid_sales, total_customer_debt, form_data)


def _extract_payment_form_data(post_data):
    """
    Extract and sanitize payment form data.
    """
    return {
        'payment_type': post_data.get('payment_type', 'debt'),
        'sale_id': post_data.get('sale_id'),
        'amount': post_data.get('amount'),
        'payment_method': post_data.get('payment_method'),
        'payment_date': post_data.get('payment_date'),
        'reference_number': post_data.get('reference_number', ''),
        'notes': post_data.get('notes', ''),
    }


def _validate_payment_form_data(form_data):
    """
    Validate payment form data and return error message if invalid.
    """
    # Check required fields
    if not form_data['amount']:
        return "Payment amount is required"
    
    if not form_data['payment_method']:
        return "Payment method is required"
    
    if not form_data['payment_date']:
        return "Payment date is required"
    
    # Validate amount
    try:
        amount = Decimal(form_data['amount'])
        if amount <= Decimal('0'):
            return "Payment amount must be positive"
    except (ValueError, InvalidOperation):
        return "Invalid payment amount format"
    
    return None


def _process_invoice_payment(request, customer, form_data):
    """
    Process payment for a specific sale/invoice.
    """
    from inventory.models import Sale, Payment
    
    try:
        amount = Decimal(form_data['amount'])
        sale = Sale.objects.get(id=form_data['sale_id'], customer=customer)
        
        # Get current balance with proper validation
        current_balance = _calculate_sale_balance(sale)
        
        # Validate payment amount
        if amount > current_balance:
            messages.error(
                request, 
                f"Payment amount (UGX {amount:,.0f}) exceeds invoice balance (UGX {current_balance:,.0f})"
            )
            return _render_payment_form_with_error(request, customer, [], customer.balance, form_data)
        
        # Process the payment
        payment_date = _parse_payment_date(form_data['payment_date'])
        
        # Create payment record
        payment = Payment.objects.create(
            sale=sale,
            amount=amount,
            payment_method=form_data['payment_method'],
            payment_date=payment_date,
            reference_number=form_data['reference_number'],
            notes=form_data['notes'],
            received_by=request.user
        )
        
        # Update sale paid amount correctly
        _update_sale_payment(sale, amount, current_balance)
        
        messages.success(
            request,
            f"Payment of UGX {amount:,.0f} applied to invoice {sale.document_number}. "
            f"Remaining balance: UGX {sale.balance_due:,.0f}"
        )
        
        return redirect('transactions:customer_detail', customer_id=customer.id)
        
    except Sale.DoesNotExist:
        messages.error(request, "Selected invoice not found or doesn't belong to this customer")
    except Exception as e:
        messages.error(request, f"Error processing invoice payment: {str(e)}")
        logger.error(f"Invoice payment error: {e}", exc_info=True)
    
    return _render_payment_form_with_error(request, customer, [], customer.balance, form_data)


def _process_manual_debt_payment(request, customer, form_data):
    """
    Process payment for general customer debt.
    """
    from .models import DebtTransaction
    
    try:
        amount = Decimal(form_data['amount'])
        customer_debt = Decimal(str(customer.balance)) if customer.balance else Decimal('0')
        
        # Validate payment amount
        if amount > customer_debt:
            messages.error(
                request,
                f"Payment amount (UGX {amount:,.0f}) exceeds customer debt (UGX {customer_debt:,.0f})"
            )
            return _render_payment_form_with_error(request, customer, [], customer.balance, form_data)
        
        # Process the payment
        payment_date = _parse_payment_date(form_data['payment_date'])
        
        # Record payment transaction
        DebtTransaction.objects.create(
            customer=customer,
            amount=float(amount),
            transaction_type='payment',
            notes=f"Payment received: {form_data['notes']}",
            reference=form_data['reference_number'],
            created_by=request.user
        )
        
        # Update customer balance
        new_balance = customer_debt - amount
        customer.balance = float(new_balance)
        customer.save()
        
        messages.success(
            request,
            f"Payment of UGX {amount:,.0f} applied to manual debt. "
            f"Remaining debt: UGX {new_balance:,.0f}"
        )
        
        return redirect('transactions:customer_detail', customer_id=customer.id)
        
    except Exception as e:
        messages.error(request, f"Error processing manual debt payment: {str(e)}")
        logger.error(f"Manual debt payment error: {e}", exc_info=True)
    
    return _render_payment_form_with_error(request, customer, [], customer.balance, form_data)


def _parse_payment_date(date_string):
    """
    Parse payment date string to timezone-aware datetime.
    """
    from django.utils.dateparse import parse_datetime
    
    payment_date = parse_datetime(date_string)
    if payment_date and timezone.is_naive(payment_date):
        payment_date = timezone.make_aware(payment_date)
    
    return payment_date or timezone.now()


def _update_sale_payment(sale, amount, current_balance):
    """
    Update sale paid amount correctly based on payment type.
    """
    if hasattr(sale, 'paid_amount'):
        # For full payment, set paid_amount to total_amount
        if amount >= current_balance:
            sale.paid_amount = sale.total_amount
        else:
            # For partial payment, add to existing paid amount
            current_paid = Decimal(str(sale.paid_amount)) if sale.paid_amount else Decimal('0')
            sale.paid_amount = current_paid + amount
        
        sale.save()


def _render_payment_form_with_error(request, customer, unpaid_sales, total_customer_debt, form_data):
    """
    Render payment form with current data when there's an error.
    """
    total_sales_balance = sum(sale.calculated_balance for sale in unpaid_sales) if unpaid_sales else Decimal('0')
    
    context = {
        "customer": customer,
        "unpaid_sales": unpaid_sales,
        "total_sales_balance": total_sales_balance,
        "total_customer_debt": total_customer_debt,
      "default_date": timezone.now().strftime(r'%Y-%m-%d\T%H:%M'),
        "initial_payment_type": form_data['payment_type'],
        "initial_sale_id": form_data['sale_id'] or '',
        "preselected_sale_id": form_data['sale_id'] or '',
        "form_data": form_data,  # Pass form data back for repopulation
    }
    return render(request, "transactions/unified_payment_form.html", context)
