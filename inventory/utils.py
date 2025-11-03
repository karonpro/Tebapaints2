from django.db.models import Q

def get_user_locations(user):
    """Get locations accessible by the user"""
    from core.models import Location, UserProfile
    
    # Ensure user has a profile
    if not hasattr(user, 'profile'):
        UserProfile.objects.get_or_create(user=user)
    
    if user.profile.can_access_all_locations:
        # Admin users can access all locations
        return Location.objects.all()
    elif user.profile.assigned_location:
        # Regular users can only access their assigned location
        return Location.objects.filter(id=user.profile.assigned_location.id)
    else:
        # Users with no location assigned get empty queryset
        return Location.objects.none()

def get_user_default_location(user):
    """Get user's default location for forms"""
    if hasattr(user, 'profile') and user.profile.assigned_location:
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