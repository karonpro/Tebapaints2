from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

router = DefaultRouter()
router.register(r'products', api_views.ProductViewSet, basename='product')
router.register(r'categories', api_views.CategoryViewSet, basename='category')
router.register(r'suppliers', api_views.SupplierViewSet, basename='supplier')
router.register(r'purchases', api_views.PurchaseViewSet, basename='purchase')
router.register(r'sales', api_views.SaleViewSet, basename='sale')
router.register(r'stock-levels', api_views.ProductStockViewSet, basename='stock-level')
router.register(r'purchase-orders', api_views.PurchaseOrderViewSet, basename='purchase-order')
router.register(r'sale-orders', api_views.SaleOrderViewSet, basename='sale-order')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/stats/', api_views.DashboardStatsAPI.as_view(), name='api_dashboard_stats'),
    path('products/<int:pk>/stock/', api_views.ProductStockDetailAPI.as_view(), name='api_product_stock'),
    path('locations/<int:location_id>/stock/', api_views.LocationStockAPI.as_view(), name='api_location_stock'),
    path('quick-sale/', api_views.QuickSaleAPI.as_view(), name='api_quick_sale'),
    path('quick-purchase/', api_views.QuickPurchaseAPI.as_view(), name='api_quick_purchase'),
    path('reports/low-stock/', api_views.LowStockReportAPI.as_view(), name='api_low_stock_report'),
    path('reports/sales/', api_views.SalesReportAPI.as_view(), name='api_sales_report'),
    path('search/products/', api_views.ProductSearchAPI.as_view(), name='api_product_search'),
]