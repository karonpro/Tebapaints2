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
    # Railway automatically sets RAILWAY_STATIC_URL
    railway_domain = os.getenv('RAILWAY_STATIC_URL', 'your-app.up.railway.app')
    ALLOWED_HOSTS = [railway_domain, 'localhost', '127.0.0.1']
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
    
    'axes',

    # Local Apps
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

    # Third Party
    'allauth.account.middleware.AccountMiddleware',
    'axes.middleware.AxesMiddleware',

    # Custom (keep these at the end)
    'core.middleware.SessionErrorMiddleware',
    'core.middleware.LocationAccessMiddleware',
]

ROOT_URLCONF = 'teba.urls'

# =======================
# TEMPLATES
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
                'core.context_processors.user_locations',
            ],
        },
    },
]

WSGI_APPLICATION = 'teba.wsgi.application'

# =======================
# DATABASE - OPTIMIZED FOR RAILWAY (FIXED)
# =======================

if IS_RAILWAY:
    # Railway PostgreSQL - FIXED VERSION
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
# STATIC FILES - OPTIMIZED FOR RAILWAY
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
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True

# Production security
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
# AXES (Login Security)
# =======================

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # 1 hour
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'account/lockout.html'
AXES_NEVER_LOCKOUT_URLS = [
    '/core/verify-login/',
    '/core/verify-email-signup/',
    '/core/session-test/',
]

# =======================
# ALLAUTH CONFIGURATION
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

# Rate limiting
ACCOUNT_RATE_LIMITS = {
    'login_failed': '5/5m',
    'confirm_email': '3/1h',
    'signup': '10/1h',
    'password_reset': '3/1h',
}

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
# EMAIL - SENDGRID CONFIGURATION
# =======================

# SendGrid Configuration
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')

if SENDGRID_API_KEY:
    # Production - SendGrid SMTP
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.sendgrid.net'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = 'apikey'
    EMAIL_HOST_PASSWORD = SENDGRID_API_KEY
else:
    # Development - Console emails
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
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =======================
# LOGGING
# =======================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{'
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if IS_PRODUCTION else 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG' if not IS_PRODUCTION else 'INFO',
            'propagate': False,
        },
        'axes': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
