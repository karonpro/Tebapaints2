from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q, F, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from .models import *
from .serializers import *
from core.utils import get_user_locations, filter_queryset_by_user_locations

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Product.objects.select_related('category').prefetch_related('stocks')
        queryset = filter_queryset_by_user_locations(queryset, self.request.user)
        
        # Apply filters
        search = self.request.query_params.get('search')
        category = self.request.query_params.get('category')
        stock_status = self.request.query_params.get('stock_status')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(sku__icontains=search)
            )
        
        if category:
            queryset = queryset.filter(category_id=category)
            
        if stock_status:
            user_locations = get_user_locations(self.request.user)
            if stock_status == 'low':
                queryset = queryset.filter(
                    stocks__location__in=user_locations,
                    stocks__quantity__lt=F('reorder_level')
                ).distinct()
            elif stock_status == 'out':
                queryset = queryset.filter(
                    stocks__location__in=user_locations,
                    stocks__quantity=0
                ).distinct()
        
        return queryset
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['user'] = self.request.user
        return context
    
    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        product = self.get_object()
        user_locations = get_user_locations(request.user)
        stocks = ProductStock.objects.filter(
            product=product, 
            location__in=user_locations
        ).select_related('location')
        
        serializer = ProductStockSerializer(stocks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        user_locations = get_user_locations(request.user)
        low_stock_products = Product.objects.filter(
            stocks__location__in=user_locations,
            stocks__quantity__lt=F('reorder_level')
        ).distinct()
        
        page = self.paginate_queryset(low_stock_products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(low_stock_products, many=True)
        return Response(serializer.data)

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Category.objects.all().order_by('name')

class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Supplier.objects.all().order_by('name')

class PurchaseViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Purchase.objects.select_related('location', 'created_by').prefetch_related('items__product')
        queryset = filter_queryset_by_user_locations(queryset, self.request.user)
        return queryset.order_by('-purchase_date')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Sale.objects.select_related('customer', 'location', 'created_by').prefetch_related('items__product')
        queryset = filter_queryset_by_user_locations(queryset, self.request.user)
        return queryset.order_by('-date')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        sale = self.get_object()
        amount = request.data.get('amount')
        payment_method = request.data.get('payment_method', 'cash')
        
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment = Payment.objects.create(
                sale=sale,
                amount=amount,
                payment_method=payment_method,
                received_by=request.user
            )
            
            # Update sale status
            sale.update_payment_status()
            
            return Response({
                'success': True,
                'payment_id': payment.id,
                'balance_due': float(sale.balance_due)
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ProductStockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductStockSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user_locations = get_user_locations(self.request.user)
        queryset = ProductStock.objects.filter(
            location__in=user_locations
        ).select_related('product', 'location')
        
        product_id = self.request.query_params.get('product_id')
        location_id = self.request.query_params.get('location_id')
        
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if location_id:
            queryset = queryset.filter(location_id=location_id)
            
        return queryset

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related('location', 'created_by').prefetch_related('items__product')
        queryset = filter_queryset_by_user_locations(queryset, self.request.user)
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_received(self, request, pk=None):
        purchase_order = self.get_object()
        
        try:
            purchase_order.mark_received()
            return Response({'success': True, 'message': 'Purchase order marked as received'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class SaleOrderViewSet(viewsets.ModelViewSet):
    serializer_class = SaleOrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = SaleOrder.objects.select_related('customer', 'location', 'created_by').prefetch_related('items__product')
        queryset = filter_queryset_by_user_locations(queryset, self.request.user)
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        sale_order = self.get_object()
        
        try:
            sale_order.confirm_order()
            return Response({'success': True, 'message': 'Sale order confirmed'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# Additional API Views
class DashboardStatsAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_locations = get_user_locations(request.user)
        
        # Total products
        total_products = Product.objects.filter(
            stocks__location__in=user_locations
        ).distinct().count()
        
        # Sales statistics (last 30 days)
        last_30_days = timezone.now() - timedelta(days=30)
        
        total_sales = Sale.objects.filter(
            location__in=user_locations,
            date__gte=last_30_days
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Purchase statistics (last 30 days)
        total_purchases = Purchase.objects.filter(
            location__in=user_locations,
            purchase_date__gte=last_30_days
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Low stock products
        low_stock_count = Product.objects.filter(
            stocks__location__in=user_locations,
            stocks__quantity__lt=F('reorder_level')
        ).distinct().count()
        
        # Inventory value
        inventory_value = ProductStock.objects.filter(
            location__in=user_locations
        ).aggregate(
            total_value=Sum(F('quantity') * F('product__cost_price'))
        )['total_value'] or 0
        
        return Response({
            'total_products': total_products,
            'total_sales': float(total_sales),
            'total_purchases': float(total_purchases),
            'low_stock_count': low_stock_count,
            'inventory_value': float(inventory_value),
        })

class ProductStockDetailAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        product = get_object_or_404(Product, id=pk)
        user_locations = get_user_locations(request.user)
        
        stocks = ProductStock.objects.filter(
            product=product,
            location__in=user_locations
        ).select_related('location')
        
        serializer = ProductStockSerializer(stocks, many=True)
        return Response(serializer.data)

class QuickSaleAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            product_id = request.data.get('product_id')
            location_id = request.data.get('location_id')
            quantity = int(request.data.get('quantity', 1))
            
            product = get_object_or_404(Product, id=product_id)
            location = get_object_or_404(Location, id=location_id)
            
            # Check stock
            stock = get_object_or_404(
                ProductStock, 
                product=product, 
                location=location,
                quantity__gte=quantity
            )
            
            # Create sale
            sale = Sale.objects.create(
                customer=None,  # Walk-in customer
                location=location,
                total_amount=quantity * product.selling_price,
                document_type='invoice',
                document_status='sent',
                created_by=request.user
            )
            
            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=product.selling_price,
                total_price=quantity * product.selling_price
            )
            
            # Update stock
            stock.quantity -= quantity
            stock.save()
            
            return Response({
                'success': True,
                'sale_id': sale.id,
                'document_number': sale.document_number,
                'total_amount': float(sale.total_amount)
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class LowStockReportAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_locations = get_user_locations(request.user)
        
        low_stock_products = Product.objects.filter(
            stocks__location__in=user_locations,
            stocks__quantity__lt=F('reorder_level')
        ).distinct().select_related('category')
        
        product_data = []
        for product in low_stock_products:
            stocks = ProductStock.objects.filter(
                product=product,
                location__in=user_locations
            )
            
            total_stock = sum(stock.quantity for stock in stocks)
            needed_stock = product.reorder_level - total_stock
            
            product_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category': product.category.name if product.category else None,
                'current_stock': total_stock,
                'reorder_level': product.reorder_level,
                'needed_stock': needed_stock,
                'cost_price': float(product.cost_price),
                'total_cost': float(needed_stock * product.cost_price)
            })
        
        return Response({'products': product_data})

class ProductSearchAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        
        if not query:
            return Response({'products': []})
        
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(sku__icontains=query)
        ).select_related('category')[:10]
        
        serializer = ProductSerializer(products, many=True)
        return Response({'products': serializer.data})

# Simple test view
from rest_framework.decorators import api_view

@api_view(['GET'])
def api_test(request):
    return Response({
        'message': 'API is working!',
        'status': 'success'
    })

class LocationStockAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, location_id):
        # Check if user can access this location
        location = get_object_or_404(Location, id=location_id)
        if not can_user_access_location(request.user, location):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        # Get all stock for this location
        stocks = ProductStock.objects.filter(
            location=location
        ).select_related('product', 'product__category')
        
        stock_data = []
        total_value = 0
        
        for stock in stocks:
            stock_value = stock.quantity * stock.product.cost_price
            total_value += stock_value
            
            stock_data.append({
                'product_id': stock.product.id,
                'product_name': stock.product.name,
                'sku': stock.product.sku,
                'category': stock.product.category.name if stock.product.category else None,
                'quantity': stock.quantity,
                'cost_price': float(stock.product.cost_price),
                'stock_value': float(stock_value),
                'reorder_level': stock.product.reorder_level,
                'status': 'low_stock' if stock.quantity < stock.product.reorder_level else 'ok' if stock.quantity > 0 else 'out_of_stock'
            })
        
        return Response({
            'location': {
                'id': location.id,
                'name': location.name
            },
            'stocks': stock_data,
            'total_products': len(stock_data),
            'total_value': float(total_value),
            'low_stock_count': len([s for s in stock_data if s['status'] == 'low_stock']),
            'out_of_stock_count': len([s for s in stock_data if s['status'] == 'out_of_stock'])
        })
    
   # ... your existing code ...

class QuickPurchaseAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            product_id = request.data.get('product_id')
            location_id = request.data.get('location_id')
            quantity = int(request.data.get('quantity', 1))
            supplier_name = request.data.get('supplier_name', 'Quick Supplier')
            unit_price = float(request.data.get('unit_price', 0))
            
            product = get_object_or_404(Product, id=product_id)
            location = get_object_or_404(Location, id=location_id)
            
            if unit_price <= 0:
                unit_price = product.cost_price
            
            # Create purchase
            purchase = Purchase.objects.create(
                supplier_name=supplier_name,
                location=location,
                total_amount=quantity * unit_price,
                created_by=request.user
            )
            
            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=quantity,
                unit_price=unit_price
            )
            
            return Response({
                'success': True,
                'purchase_id': purchase.id,
                'reference': purchase.reference,
                'total_amount': float(purchase.total_amount)
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class SalesReportAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Add your sales report logic here
        return Response({'message': 'Sales report endpoint'})

# Simple test view
from rest_framework.decorators import api_view

@api_view(['GET'])
def api_test(request):
    return Response({
        'message': 'API is working!',
        'status': 'success'
    })