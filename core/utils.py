# core/utils.py
from django.db.models import Q
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from functools import wraps
import logging

# core/utils.py
from django.db.models import Q
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from functools import wraps
import logging

logger = logging.getLogger(__name__)

def get_user_locations(user):
    """Get locations accessible by the user"""
    if not user.is_authenticated:
        from inventory.models import Location  # Changed from core.models
        return Location.objects.none()
    
    cache_key = f"user_locations_{user.id}"
    cached_locations = cache.get(cache_key)
    
    if cached_locations is not None:
        return cached_locations
    
    try:
        from inventory.models import Location  # Changed from core.models
        from core.models import UserProfile
        
        # Ensure user has a profile
        if not hasattr(user, 'profile'):
            UserProfile.objects.get_or_create(user=user)
        
        profile = user.profile
        
        # Use the property correctly - get the profile object first
        if profile.can_access_all_locations:  # This uses the @property
            # Admin users can access all locations
            locations = Location.objects.all()
        elif profile.assigned_location:
            # Regular users can only access their assigned location
            locations = Location.objects.filter(id=profile.assigned_location.id)
        else:
            # Users with no location assigned get empty queryset
            logger.warning(f"User {user.username} has no assigned location")
            locations = Location.objects.none()
        
        # Cache for 5 minutes
        cache.set(cache_key, locations, 300)
        return locations
        
    except Exception as e:
        logger.error(f"Error getting user locations for {user.username}: {str(e)}")
        from inventory.models import Location  # Changed from core.models
        return Location.objects.none()

# ... rest of your utility functions remain the same


def get_user_default_location(user):
    """Get user's default location for forms"""
    if user.is_authenticated and hasattr(user, 'profile') and user.profile.assigned_location:
        return user.profile.assigned_location
    return None

def can_user_access_location(user, location):
    """Check if user can access a specific location"""
    user_locations = get_user_locations(user)
    return location in user_locations

def filter_queryset_by_user_locations(queryset, user, location_field='location'):
    """Filter any queryset by user's accessible locations"""
    user_locations = get_user_locations(user)
    if user_locations.exists():
        filter_kwargs = {f'{location_field}__in': user_locations}
        return queryset.filter(**filter_kwargs)
    return queryset.none()

def get_user_location_ids(user):
    """Get list of location IDs accessible by user"""
    locations = get_user_locations(user)
    return list(locations.values_list('id', flat=True))

def clear_user_locations_cache(user):
    """Clear cache for user locations (call when user permissions change)"""
    cache_key = f"user_locations_{user.id}"
    cache.delete(cache_key)

# Additional utility functions for enhanced functionality

def require_location_access(view_func):
    """Decorator to ensure user has access to location in view"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user_locations = get_user_locations(request.user)
        
        # If user has no location access, deny permission
        if not user_locations.exists():
            raise PermissionDenied("You don't have access to any locations.")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def require_specific_location_access(location_param='location_id'):
    """Decorator factory for specific location access"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            location_id = kwargs.get(location_param)
            if location_id:
                try:
                    from core.models import Location
                    location = Location.objects.get(id=location_id)
                    if not can_user_access_location(request.user, location):
                        raise PermissionDenied(f"No access to location: {location.name}")
                except Location.DoesNotExist:
                    raise PermissionDenied("Location not found")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def get_user_accessible_location_names(user):
    """Get list of location names accessible by user"""
    locations = get_user_locations(user)
    return list(locations.values_list('name', flat=True))

def assert_user_can_access_location(user, location, raise_exception=True):
    """Assert that user can access a location, optionally raising exception"""
    can_access = can_user_access_location(user, location)
    
    if not can_access and raise_exception:
        raise PermissionDenied(f"You don't have permission to access location: {location.name}")
    
    return can_access

# Specialized filter functions for common models
def filter_sales_by_user_locations(queryset, user):
    """Specialized filter for sales"""
    return filter_queryset_by_user_locations(queryset, user, 'location')

def filter_purchases_by_user_locations(queryset, user):
    """Specialized filter for purchases"""
    return filter_queryset_by_user_locations(queryset, user, 'location')

def filter_stock_by_user_locations(queryset, user):
    """Specialized filter for product stock"""
    return filter_queryset_by_user_locations(queryset, user, 'location')

def filter_transfers_by_user_locations(queryset, user):
    """Specialized filter for transfers (from_location)"""
    return filter_queryset_by_user_locations(queryset, user, 'from_location')

def get_location_choices_for_user(user):
    """Get location choices for forms"""
    locations = get_user_locations(user)
    return [(loc.id, loc.name) for loc in locations]

def get_default_location_for_user(user):
    """Get default location for user (for forms)"""
    default_location = get_user_default_location(user)
    if default_location:
        return default_location
    
    # Fallback: first accessible location
    locations = get_user_locations(user)
    if locations.exists():
        return locations.first()
    
    return None