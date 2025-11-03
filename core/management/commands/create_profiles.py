from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile

class Command(BaseCommand):
    help = 'Create profiles for all users'

    def handle(self, *args, **options):
        users = User.objects.all()
        created_count = 0
        
        for user in users:
            try:
                # Check if profile already exists
                if hasattr(user, 'profile'):
                    self.stdout.write(f'→ Profile exists for: {user.username}')
                else:
                    # Create new profile
                    UserProfile.objects.create(user=user)
                    self.stdout.write(f'✓ Created profile for: {user.username}')
                    created_count += 1
            except Exception as e:
                self.stdout.write(f'✗ Error for {user.username}: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} profiles. Total users: {users.count()}')
        )