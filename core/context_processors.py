from .utils import get_user_locations, get_user_default_location

def user_locations(request):
    """Make user location info available in all templates"""
    if request.user.is_authenticated:
        return {
            'user_locations': get_user_locations(request.user),
            'user_default_location': get_user_default_location(request.user),
            'user_can_access_all_locations': request.user.profile.can_access_all_locations if hasattr(request.user, 'profile') else False,
        }
    return {}