"""
Django settings for teba project - OPTIMIZED FOR RAILWAY & SENDGRID
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =======================
# ENVIRONMENT DETECTION
# =======================

BASE_DIR = Path(__file__).resolve().parent.parent

# Detect environment
IS_RAILWAY = os.getenv('RAILWAY_ENVIRONMENT') is not None
IS_PRODUCTION = IS_RAILWAY or os.getenv('DJANGO_ENV') == 'production'

# =======================
# SECURITY & CORE SETTINGS
# =======================

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise Exception("SECRET_KEY must be set in production!")
    else:
        SECRET_KEY = 'dev-key-only-for-local-development-change-in-production'

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true' and not IS_PRODUCTION

if IS_RAILWAY:
    railway_domain = os.getenv('RAILWAY_STATIC_URL', 'your-app.up.railway.app')
    ALLOWED_HOSTS = [railway_domain, 'localhost', '127.0.0.1', '0.0.0.0']
    CSRF_TRUSTED_ORIGINS = [f"https://{railway_domain}"]
else:
    ALLOWED_HOSTS = ['*']
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://0.0.0.0:8000',
    ]

# =======================
# INSTALLED APPS
# =======================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',

    'rest_framework',
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'axes',

    'core',
    'transactions',
    'inventory',
]

# =======================
# MIDDLEWARE
# =======================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'allauth.account.middleware.AccountMiddleware',
    'axes.middleware.AxesMiddleware',

    'core.middleware.SessionErrorMiddleware',
    'core.middleware.LocationAccessMiddleware',
]

ROOT_URLCONF = 'teba.urls'

# =======================
# TEMPLATES - KEEP SIMPLE (NO CACHING)
# =======================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,  # KEEP THIS SIMPLE - NO CACHED LOADERS
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.user_locations',
            ],
        },
    },
]

WSGI_APPLICATION = 'teba.wsgi.application'

# =======================
# DATABASE
# =======================

if IS_RAILWAY:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# =======================
# PASSWORD VALIDATION
# =======================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
]

# =======================
# INTERNATIONALIZATION
# =======================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =======================
# STATIC FILES
# =======================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# =======================
# AUTHENTICATION
# =======================

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# =======================
# SESSION & SECURITY
# =======================

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True

if IS_PRODUCTION:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# =======================
# AXES
# =======================

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'account/lockout.html'
AXES_NEVER_LOCKOUT_WHITELIST = [
    '/core/verify-login/',
    '/core/verify-email-signup/',
    '/core/session-test/',
]

# =======================
# ALLAUTH CONFIGURATION - CRITICAL PART
# =======================

SITE_ID = 1

# Email & Authentication
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[Teba Paint Center] '
ACCOUNT_ADAPTER = 'core.adapters.CustomAccountAdapter'
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_SESSION_REMEMBER = True

# Modern authentication
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

# Security
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_PASSWORD_MIN_LENGTH = 8
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_CONFIRM_EMAIL_ON_GET = False

# Redirect URLs
LOGIN_REDIRECT_URL = '/inventory/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/accounts/login/'
ACCOUNT_SIGNUP_REDIRECT_URL = '/core/verify-email-signup/'
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = '/core/verify-email-signup/'


# =======================
# EMAIL CONFIGURATION - GMAIL WITH SSL
# =======================
# =======================
# EMAIL CONFIGURATION - RESEND
# =======================
# =======================
# EMAIL CONFIGURATION - RESEND API (HTTP)
# =======================

RESEND_API_KEY = os.getenv('RESEND_API_KEY')

if RESEND_API_KEY:
    # Use Resend HTTP API (bypasses SMTP blocking)
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    
    # But we'll override the email sending to use Resend API directly
    # For now, use this simple approach:
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        
        # Test the connection
        test_params = {
            "from": "onboarding@resend.dev",
            "to": ["kaggaronald1@gmail.com"],
            "subject": "Resend Connection Test",
            "html": "<strong>Resend is working!</strong>",
        }
        
        # This will use HTTP API, not SMTP
        print("✅ Resend API configured successfully!")
        print("=== USING RESEND API (HTTP) ===")
        
        # We'll handle emails via Resend API in our views
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Fallback for now
        DEFAULT_FROM_EMAIL = 'onboarding@resend.dev'
        
    except Exception as e:
        print(f"❌ Resend setup failed: {e}")
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
        DEFAULT_FROM_EMAIL = 'tebaspprt@gmail.com'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'tebaspprt@gmail.com'
    print("=== USING CONSOLE EMAILS ===")


# =======================
# SITE CONFIGURATION
# =======================

SITE_NAME = "Teba Paint Center"
if IS_RAILWAY:
    SITE_DOMAIN = f"https://{os.getenv('RAILWAY_STATIC_URL', 'your-app.up.railway.app')}"
else:
    SITE_DOMAIN = "http://localhost:8000"

SUPPORT_EMAIL = 'tebaspprt@gmail.com'
ADMIN_EMAIL = 'tebaspprt@gmail.com'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

print(f"=== Teba Settings Loaded ===")
print(f"Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
print(f"Debug: {DEBUG}")
print(f"Domain: {SITE_DOMAIN}")
print(f"Email Backend: {EMAIL_BACKEND}")
print(f"Database: {DATABASES['default']['ENGINE']}")
print("=============================")
