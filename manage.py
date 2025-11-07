#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teba.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # ----------------- AUTO CREATE SUPERUSER SNIPPET -----------------
    if 'createsuperuser' in sys.argv:
        import django
        django.setup()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            print("Creating superuser...")
            User.objects.create_superuser(
                username="kagga",
                email="kaggaronald1@gmail.com",
                password="karon1294"
            )
        else:
            print("Superuser already exists")
        sys.exit()
    # ------------------------------------------------------------------

    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
