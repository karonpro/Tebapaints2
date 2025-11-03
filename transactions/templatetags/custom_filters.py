from django import template

register = template.Library()

@register.filter
def sum_field(queryset, field_name):
    """Sum a numeric field for a queryset or list of objects."""
    if not queryset:
        return 0
    total = 0
    for obj in queryset:
        value = getattr(obj, field_name, 0)
        try:
            total += float(value or 0)
        except (TypeError, ValueError):
            total += 0
    return total


@register.filter
def abs_value(value):
    """Return the absolute (positive) value of a number."""
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0
