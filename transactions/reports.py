from datetime import date
from django.db.models import Sum
from sales.models import Sale
from transactions.models import Payment, Customer


class CustomerReport:
    """Global reporting manager for all customers with date & branch filters"""

    @staticmethod
    def wholesale_total(start=None, end=None, branch=None):
        qs = Sale.objects.filter(payment_type=Sale.PAYMENT_CASH)
        if branch: qs = qs.filter(branch=branch)
        if start: qs = qs.filter(created_at__date__gte=start)
        if end: qs = qs.filter(created_at__date__lte=end)
        return qs.aggregate(total=Sum("total_amount"))["total"] or 0

    @staticmethod
    def debt_total(start=None, end=None, branch=None):
        qs = Sale.objects.filter(payment_type=Sale.PAYMENT_DEBT)
        if branch: qs = qs.filter(branch=branch)
        if start: qs = qs.filter(created_at__date__gte=start)
        if end: qs = qs.filter(created_at__date__lte=end)
        return qs.aggregate(total=Sum("total_amount"))["total"] or 0

    @staticmethod
    def account_total(start=None, end=None, branch=None):
        qs = Sale.objects.filter(payment_type=Sale.PAYMENT_ACCOUNT)
        if branch: qs = qs.filter(branch=branch)
        if start: qs = qs.filter(created_at__date__gte=start)
        if end: qs = qs.filter(created_at__date__lte=end)
        return qs.aggregate(total=Sum("total_amount"))["total"] or 0

    @staticmethod
    def payments_total(start=None, end=None, branch=None):
        qs = Payment.objects.all()
        if branch: qs = qs.filter(branch=branch)
        if start: qs = qs.filter(date__gte=start)
        if end: qs = qs.filter(date__lte=end)
        return qs.aggregate(total=Sum("amount"))["total"] or 0

    @staticmethod
    def customer_balances(branch=None):
        """Get each customer's current balance per branch"""
        qs = Customer.objects.all()
        if branch:
            qs = qs.filter(branch=branch)
        return qs.values("id", "name", "balance").order_by("name")
