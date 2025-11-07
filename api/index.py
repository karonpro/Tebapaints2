import os
import sys
import traceback

def handler(request, response):
    try:
        # Add project root to Python path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        sys.path.insert(0, project_root)
        
        # Set Django settings
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teba.settings')
        
        # Force print to logs
        print("=== STARTING DJANGO SETUP ===")
        print(f"Python path: {sys.path}")
        print(f"Current directory: {os.getcwd()}")
        
        # Try to import Django
        try:
            import django
            print(f"✅ Django imported: {django.__version__}")
        except ImportError as e:
            print(f"❌ Django import failed: {e}")
            raise
        
        # Try to configure Django
        try:
            from django.conf import settings
            print("✅ Django settings imported")
            
            if not settings.configured:
                print("❌ Settings not configured")
                raise Exception("Django settings not configured")
                
            print("✅ Settings are configured")
        except Exception as e:
            print(f"❌ Settings configuration failed: {e}")
            raise
        
        # Try to setup Django
        try:
            django.setup()
            print("✅ Django setup completed")
        except Exception as e:
            print(f"❌ Django setup failed: {e}")
            raise
        
        # Try to get WSGI application
        try:
            from django.core.wsgi import get_wsgi_application
            application = get_wsgi_application()
            print("✅ WSGI application loaded")
        except Exception as e:
            print(f"❌ WSGI application failed: {e}")
            raise
        
        print("=== DJANGO SETUP COMPLETE ===")
        return application
        
    except Exception as e:
        # Capture full error details
        error_traceback = traceback.format_exc()
        
        # Print everything to Vercel logs
        print("=== FULL ERROR TRACEBACK ===")
        print(error_traceback)
        print("=== END ERROR ===")
        
        # Return minimal error response
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain'},
            'body': 'Server Error - Check Vercel logs for details'
        }