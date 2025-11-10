"""
Django settings for teba project - OPTIMIZED FOR RAILWAY
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
    # Railway automatically sets RAILWAY_STATIC_URL
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
    # Django Core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',

    # Third Party
    'rest_framework',
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'axes',

    # Local Apps
    'core',
    'transactions',
    'inventory',
]

# =======================
# MIDDLEWARE - SIMPLIFIED TO FIX REDIRECTS
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

    # Third Party
    'axes.middleware.AxesMiddleware',
    'allauth.account.middleware.AccountMiddleware',

    # COMMENT OUT custom middleware temporarily to fix redirects
    # 'core.middleware.SessionErrorMiddleware',
    # 'core.middleware.LocationAccessMiddleware',
]

ROOT_URLCONF = 'teba.urls'

# =======================
# TEMPLATES - FIXED CONFIGURATION
# =======================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 'core.context_processors.user_locations',  # Comment out if missing
            ],
        },
    },
]

# Template caching in production
if IS_PRODUCTION:
    TEMPLATES[0]['APP_DIRS'] = False
    TEMPLATES[0]['OPTIONS']['loaders'] = [
        ('django.template.loaders.cached.Loader', [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ]),
    ]

WSGI_APPLICATION = 'teba.wsgi.application'

# =======================
# DATABASE - OPTIMIZED FOR RAILWAY
# =======================

if IS_RAILWAY:
    # Railway PostgreSQL
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    # Development - SQLite
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
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
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
# STATIC FILES - OPTIMIZED FOR RAILWAY
# =======================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_MANIFEST_STRICT = False

# =======================
# AUTHENTICATION - SIMPLIFIED
# =======================

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    # 'axes.backends.AxesStandaloneBackend',  # Comment out temporarily
]

# =======================
# SESSION & SECURITY
# =======================

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True

# Production security
if IS_PRODUCTION:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = True
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# =======================
# AXES (Login Security) - TEMPORARILY DISABLED
# =======================

AXES_ENABLED = False  # Disable temporarily to fix redirects

# =======================
# ALLAUTH CONFIGURATION - SIMPLIFIED TO FIX REDIRECTS
# =======================

SITE_ID = 1

# SIMPLIFIED AllAuth configuration - NO COMPLEX REDIRECTS
ACCOUNT_EMAIL_VERIFICATION = 'optional'  # Change from 'mandatory' to fix redirects
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[Teba Paint Center] '
ACCOUNT_LOGOUT_ON_GET = True  # Simplify logout
ACCOUNT_SESSION_REMEMBER = True

# Simple authentication settings
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False

# SIMPLE redirect URLs - no complex chains
LOGIN_REDIRECT_URL = '/inventory/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/accounts/login/'

# Security - keep simple
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_PASSWORD_MIN_LENGTH = 8
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True  # Auto login after confirmation
ACCOUNT_CONFIRM_EMAIL_ON_GET = True  # Confirm on click

# COMMENT OUT complex settings that cause redirect loops:
# ACCOUNT_ADAPTER = 'core.adapters.CustomAccountAdapter'
# ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
# ACCOUNT_LOGIN_METHODS = {'email'}
# ACCOUNT_SIGNUP_REDIRECT_URL = '/core/verify-email-signup/'
# ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = '/core/verify-email-signup/'

# =======================
# EMAIL CONFIGURATION - SIMPLE CONSOLE BACKEND
# =======================

# Simple email configuration - console only
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'tebaspprt@gmail.com')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

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
ADMINS = [('Admin', ADMIN_EMAIL)]
MANAGERS = ADMINS

# =======================
# REST FRAMEWORK
# =======================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# Only enable browsable API in development
if not IS_PRODUCTION:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'].append('rest_framework.renderers.BrowsableAPIRenderer')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =======================
# CUSTOM APPLICATION SETTINGS
# =======================

# Verification code settings
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_CODE_EXPIRY_MINUTES = 10

# Inventory settings
INVENTORY_LOW_STOCK_THRESHOLD = 10
INVENTORY_CRITICAL_STOCK_THRESHOLD = 5

print(f"=== Teba Settings Loaded ===")
print(f"Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
print(f"Debug: {DEBUG}")
print(f"Domain: {SITE_DOMAIN}")
print(f"Email Backend: {EMAIL_BACKEND}")
print(f"Database: {DATABASES['default']['ENGINE']}")
print(f"Template Caching: {'ENABLED' if IS_PRODUCTION else 'DISABLED'}")
print("=============================")
