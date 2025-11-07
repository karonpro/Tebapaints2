import os
from django.core.wsgi import get_wsgi_application

# ✅ Set your default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teba.settings')

# ✅ Create the WSGI application
application = get_wsgi_application()
