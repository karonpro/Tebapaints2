from django.urls import path
from . import views

app_name = 'transactions'

urlpatterns = [
    # ==================== HOME & DASHBOARD ====================
    path('', views.home, name='home'),

    # ==================== TRANSACTIONS ====================
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/add/', views.transaction_add, name='transaction_add'),
    path('transactions/<int:pk>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    path('transactions/<int:pk>/', views.transaction_detail, name='transaction_detail'),
    path('transactions/view/<int:id>/', views.view_transaction, name='view_transaction'),

    # ==================== CUSTOMERS ====================
    path('customers/', views.customers_list, name='customers_list'),
    path('customers/', views.customers_list, name='customers'),  # Alias 1
    path('customers/', views.customers_list, name='customer_list'),  # Alias 2
    path('customers/add/', views.customer_add, name='customer_add'),
    path('customers/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:customer_id>/ledger/', views.customer_ledger, name='customer_ledger'),
    path('customers/<int:customer_id>/add-supply/', views.add_supply, name='add_supply'),
    
    # ==================== BALANCE MANAGEMENT ====================
    path('customers/<int:customer_id>/add-balance/', views.add_customer_balance, name='add_customer_balance'),
    path('customers/<int:customer_id>/deduct-balance/', views.deduct_customer_balance, name='deduct_customer_balance'),
    path('customers/<int:customer_id>/balance-history/', views.customer_balance_history, name='customer_balance_history'),
    path('customers/<int:customer_id>/quick-adjustment/', views.quick_balance_adjustment, name='quick_balance_adjustment'),
  # urls.py - Replace the balance management URLs
    path('customers/<int:customer_id>/add-debt/', views.add_customer_debt, name='add_customer_debt'),
    path('customers/<int:customer_id>/receive-payment/', views.receive_payment, name='receive_payment'),
    path('customers/<int:customer_id>/debt-history/', views.customer_debt_history, name='customer_debt_history'),
    path('customers/<int:customer_id>/quick-supply/', views.quick_supply_debt, name='quick_supply_debt'),
    # ==================== PAYMENTS ====================
    path('payments/add/', views.payment_add, name='payment_add'),
# ==================== PAYMENTS ====================
# Remove this line: path('payments/add/', views.payment_add, name='payment_add'),
# Replace with:
    path('customers/<int:customer_id>/receive-payment/', views.receive_payment, name='receive_payment'),
    path('customers/<int:customer_id>/receive-unified-payment/', 
     views.receive_unified_payment, 
     name='receive_unified_payment'),
    # ==================== EXPENSES ====================
    path('expenses/', views.expenses_list, name='expenses_list'),  # main name
    path('expenses/', views.expenses_list, name='expenses'),       # alias for templates
    path('expenses/add/', views.expense_add, name='expense_add'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # ==================== REPORTS ====================
    path('reports/', views.report_home, name='report_home'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/daily/export/', views.daily_export, name='daily_export'),
    path('reports/customers/', views.customer_report, name='customer_report'),
    path('reports/expenses/', views.expense_report, name='expense_report'),
    path('reports/transactions/', views.transaction_report, name='transaction_report'),

    # ==================== API ENDPOINTS ====================
    path('api/customer-details/<int:customer_id>/', views.api_customer_details, name='api_customer_details'),
]