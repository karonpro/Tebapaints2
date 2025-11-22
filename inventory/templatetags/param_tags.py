from django import template

register = template.Library()

@register.simple_tag
def param_remove(request, param_name):
    """Remove a parameter from the current query string"""
    from django.http import QueryDict
    from urllib.parse import urlencode
    
    query_dict = QueryDict(mutable=True)
    query_dict.update({key: value for key, value in request.GET.items() if key != param_name})
    return urlencode(query_dict)

@register.simple_tag
def param_replace(request, **kwargs):
    """Replace or add parameters in the current query string"""
    from django.http import QueryDict
    from urllib.parse import urlencode
    
    query_dict = QueryDict(mutable=True)
    query_dict.update(request.GET)
    
    for key, value in kwargs.items():
        if value is not None:
            query_dict[key] = value
        else:
            query_dict.pop(key, None)
    
    return urlencode(query_dict)