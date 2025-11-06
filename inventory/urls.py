from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('', views.inventory_dashboard, name='dashboard'),
    
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_add, name='product_add'),
    path('products/edit/<int:pk>/', views.product_edit, name='product_edit'),
    path('products/delete/<int:pk>/', views.product_delete, name='product_delete'),
    path('products/<int:product_id>/', views.product_detail, name='product_detail'),
    path('products/batch-delete/', views.product_batch_delete, name='product_batch_delete'),
    
    # Purchases
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/add/', views.purchase_add, name='purchase_add'),
    path('purchases/delete/<int:pk>/', views.purchase_delete, name='purchase_delete'),
    path('purchases/<int:pk>/edit/', views.purchase_edit, name='purchase_edit'),  # ADDED
    
    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/add/', views.sale_add, name='sale_add'),
    path('sales/print/<int:pk>/', views.print_sale, name='print_sale'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),  # ADDED
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),  # ADDED
    
    # Stock Transfers
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/add/', views.transfer_add, name='transfer_add'),
    path('transfers/<int:batch_id>/confirm/', views.confirm_transfer, name='confirm_transfer'),
    path('transfers/<int:batch_id>/cancel/', views.cancel_transfer, name='cancel_transfer'),
    path('transfers/<int:batch_id>/', views.transfer_detail, name='transfer_detail'),

    # Reports
    path('stock-report/', views.stock_report, name='stock_report'),
    path('sales-report/', views.sales_report, name='sales_report'),
    
    # Search and API
    path('search_product/', views.search_product, name='search_product'),
    path('api/products/', views.product_search_api, name='product_search_api'),
    path('api/stock/<int:product_id>/<int:location_id>/', views.get_product_stock, name='get_product_stock'),
    
    # Payments
    path('sales/<int:sale_id>/payments/', views.sale_payments, name='sale_payments'),
    path('sales/<int:sale_id>/payments/add/', views.add_payment, name='add_payment'),
    path('payments/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),
    path('payments/<int:payment_id>/edit/', views.payment_edit, name='payment_edit'),  # ADDED
    
    # Import/Export
    path('export-products/', views.export_products_csv, name='export_products'),
    path('import-products/', views.import_products_csv, name='import_products'),
   
    # Retail Sales
    path('retail/', views.retail_sale_view, name='retail_sale'),
    path('retail/sale/', views.retail_sale_view, name='retail_sale'),
    path('retail/sales/', views.retail_sales_list, name='retail_sales_list'),
    path('retail/sales/<int:sale_id>/', views.retail_sale_detail, name='retail_sale_detail'),
    path('retail/sales/<int:sale_id>/delete/', views.delete_retail_sale, name='delete_retail_sale'),
    path('retail/stock/', views.retail_stock_view, name='retail_stock'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/add/', views.purchase_order_add, name='purchase_order_add'),
    path('purchase-orders/<int:order_id>/receive/', views.mark_purchase_received, name='mark_purchase_received'),
    path('purchase-orders/<int:pk>/delete/', views.purchase_order_delete, name='purchase_order_delete'),  # ADDED
    path('purchases/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('sale-orders/<int:pk>/', views.sale_order_detail, name='sale_order_detail'),
# Company Details
    path('company-details/', views.company_details, name='company_details'),

    # Sale Orders
    path('sale-orders/', views.sale_order_list, name='sale_order_list'),
    path('sale-orders/add/', views.sale_order_add, name='sale_order_add'),
    path('sale-orders/<int:order_id>/confirm/', views.confirm_sale_order, name='confirm_sale_order'),
    path('sale-orders/<int:pk>/delete/', views.sale_order_delete, name='sale_order_delete'),  # ADDED
    
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_add, name='supplier_add'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),
# Stocktake URLs
    path('stocktakes/', views.stocktake_list, name='stocktake_list'),
    path('stocktakes/create/', views.stocktake_create, name='stocktake_create'),
    path('stocktakes/<int:pk>/', views.stocktake_detail, name='stocktake_detail'),
    path('stocktakes/<int:pk>/delete/', views.stocktake_delete, name='stocktake_delete'),
    path('stocktakes/<int:pk>/set-uncounted-zero/', views.set_uncounted_to_zero, name='set_uncounted_zero'),
    path('sales/<int:sale_id>/payments/', views.sale_payments, name='sale_payments'),

    # ... your existing URLs ...
    
    # Reports URLs
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/sales-summary/', views.sales_summary_report, name='sales_summary_report'),
    path('reports/product-performance/', views.product_performance_report, name='product_performance_report'),
    path('reports/inventory-valuation/', views.inventory_valuation_report, name='inventory_valuation_report'),
    path('reports/purchase-analysis/', views.purchase_analysis_report, name='purchase_analysis_report'),
    path('reports/customer-analysis/', views.customer_analysis_report, name='customer_analysis_report'),
    path('reports/stock-movement/', views.stock_movement_report, name='stock_movement_report'),
    path('reports/export/<str:report_type>/', views.export_report_csv, name='export_report_csv'),
# Add this to your inventory/urls.py urlpatterns
    path('api/customer-search/', views.customer_search_api, name='customer_search_api'),
# Add these to your inventory/urls.py

# Purchase Reports
path('reports/purchase-summary/', views.purchase_summary_report, name='purchase_summary_report'),
path('reports/supplier-analysis/', views.supplier_analysis_report, name='supplier_analysis_report'),
path('reports/purchase-product-analysis/', views.purchase_product_analysis_report, name='purchase_product_analysis_report'),
path('reports/purchase-trend-analysis/', views.purchase_trend_analysis_report, name='purchase_trend_analysis_report'),
path('reports/export-purchase/<str:report_type>/', views.export_purchase_report, name='export_purchase_report'),
# Add these to your inventory/urls.py

# Transfer Reports
path('reports/transfer-summary/', views.transfer_summary_report, name='transfer_summary_report'),
path('reports/transfer-location-analysis/', views.transfer_location_analysis_report, name='transfer_location_analysis_report'),
path('reports/transfer-product-analysis/', views.transfer_product_analysis_report, name='transfer_product_analysis_report'),
path('reports/transfer-efficiency/', views.transfer_efficiency_report, name='transfer_efficiency_report'),
path('reports/export-transfer/<str:report_type>/', views.export_transfer_report, name='export_transfer_report'),
#  Product Movement Reports
path('products/<int:product_id>/movement-report/', views.product_movement_report, name='product_movement_report'),
path('products/<int:product_id>/movement-export/', views.product_movement_export, name='product_movement_export'),
] 

