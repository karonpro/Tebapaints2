from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile

class Command(BaseCommand):
    help = 'Create missing user profiles'

    def handle(self, *args, **options):
        users_without_profiles = User.objects.filter(profile__isnull=True)
        
        self.stdout.write(f'Found {users_without_profiles.count()} users without profiles')
        
        for user in users_without_profiles:
            UserProfile.objects.create(user=user)
            self.stdout.write(f'Created profile for user: {user.username}')
        
        self.stdout.write(self.style.SUCCESS('Successfully fixed all user profiles'))