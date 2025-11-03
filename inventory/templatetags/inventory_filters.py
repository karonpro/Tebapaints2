# inventory/templatetags/inventory_filters.py
from django import template

register = template.Library()

@register.filter
def dict_key(dictionary, key):
    """Get a value from a dictionary by key"""
    if dictionary and key in dictionary:
        return dictionary[key]
    return None

@register.filter
def get_item(dictionary, key):
    """Get a value from a dictionary by key (alternative name)"""
    return dict_key(dictionary, key)


    from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiply two numbers."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

from django import template

register = template.Library()

@register.filter
def remove_param(query_string, param_name):
    """
    Remove a parameter from a query string
    Usage: {{ request.GET.urlencode|remove_param:'page' }}
    """
    if not query_string:
        return ''
    
    params = query_string.split('&')
    filtered_params = [p for p in params if not p.startswith(f'{param_name}=')]
    return '&'.join(filtered_params)

@register.filter
def subtract(value, arg):
    """Subtract two numbers."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0