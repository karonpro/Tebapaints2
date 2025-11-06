import os
import sys
import traceback
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teba.settings')

try:
    application = get_wsgi_application()
except Exception as e:
    # Print full traceback to Vercel logs
    traceback.print_exc()
    raise e
