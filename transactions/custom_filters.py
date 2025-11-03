from django import template

register = template.Library()

@register.filter
def sum_field(queryset, field_name):
    """
    Usage in template:
    {{ queryset|sum_field:"amount" }}
    """
    return sum(getattr(obj, field_name, 0) or 0 for obj in queryset)


@register.filter
def abs_value(value):
    """
    Returns the absolute value of a number.
    Usage: {{ value|abs_value }}
    """
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value


@register.filter
def currency(value):
    """
    Formats a number with commas and two decimal places.
    Usage: {{ value|currency }}
    """
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return value


@register.filter
def less_excess_label(value):
    """
    Returns an HTML label for Less/Excess with colors.
    Positive = Excess (green)
    Negative = Less (red)
    Zero = Balanced (gray)
    Usage: {{ value|less_excess_label|safe }}
    """
    try:
        val = float(value)
        if val > 0:
            return f'<span style="color: green; font-weight: bold;">Excess ({val:,.2f})</span>'
        elif val < 0:
            return f'<span style="color: red; font-weight: bold;">Less ({abs(val):,.2f})</span>'
        else:
            return '<span style="color: gray;">Balanced</span>'
    except (ValueError, TypeError):
        return value

@register.filter
def abs_value(value):
    """Return absolute value for use in templates"""
    try:
        return abs(value)
    except (TypeError, ValueError):
        return 0
  
