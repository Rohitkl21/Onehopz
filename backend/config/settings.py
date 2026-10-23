"""Django settings for OneHopz backend project.

Generated for Milestone 1.3: Development Environment and Repository Setup.
Architecture Tenet: Authoritative PostgreSQL with PostGIS, Celery/Redis, DRF.
"""

import os
import sys
from pathlib import Path
from typing import Any

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv

    # Look for .env in root or backend directory
    root_env = BASE_DIR.parent / ".env"
    backend_env = BASE_DIR / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    elif backend_env.exists():
        load_dotenv(backend_env)
except ImportError:
    pass

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "onehopz-dev-insecure-secret-key-replace-in-production-1234567890",
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS_RAW = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,backend,frontend")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_RAW.split(",") if host.strip()]

ONEHOPZ_ENV = os.getenv("ONEHOPZ_ENV", "development")

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    # Internal core shared apps
    "apps.core.apps.CoreConfig",
    "apps.identity.apps.IdentityConfig",
    "apps.merchants.apps.MerchantsConfig",
]

AUTH_USER_MODEL = "identity.User"

# Conditionally include GIS app if GDAL is available or running in container
ENABLE_GIS = os.getenv("ENABLE_GIS", "auto")
if ENABLE_GIS == "true":
    INSTALLED_APPS.insert(0, "django.contrib.gis")
elif ENABLE_GIS == "auto":
    try:
        from django.contrib.gis import gdal  # noqa: F401

        INSTALLED_APPS.insert(0, "django.contrib.gis")
    except Exception:
        # GDAL not available in this host environment; proceed without GIS app
        pass

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database Configuration
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

USE_POSTGRES = os.getenv("USE_POSTGRES", "true").lower() in ("true", "1", "yes")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "onehopz_dev")
DB_USER = os.getenv("POSTGRES_USER", "onehopz_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "onehopz_dev_password")

# Select appropriate database engine (PostGIS when GIS is enabled, standard PostgreSQL or SQLite fallback)
IS_TESTING = "pytest" in sys.modules or any("pytest" in arg or "test" in arg for arg in sys.argv)

DATABASES: dict[str, Any]

if IS_TESTING and not os.path.exists("/.dockerenv") and (DB_HOST == "postgres" or not USE_POSTGRES):
    # Host test runner outside Docker container; use fast in-memory sqlite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    if USE_POSTGRES and "django.contrib.gis" in INSTALLED_APPS:
        DB_ENGINE = "django.contrib.gis.db.backends.postgis"
    elif USE_POSTGRES:
        DB_ENGINE = "django.db.backends.postgresql"
    else:
        DB_ENGINE = "django.db.backends.sqlite3"

    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": DB_NAME if USE_POSTGRES else BASE_DIR / "db.sqlite3",
            "USER": DB_USER if USE_POSTGRES else "",
            "PASSWORD": DB_PASSWORD if USE_POSTGRES else "",
            "HOST": DB_HOST if USE_POSTGRES else "",
            "PORT": DB_PORT if USE_POSTGRES else "",
            "CONN_MAX_AGE": 60,
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework Configuration
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.authentication.JSONWebTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "UNAUTHENTICATED_USER": None,
}

if DEBUG:
    # Allow browsable API in development
    default_renderers = REST_FRAMEWORK.get("DEFAULT_RENDERER_CLASSES")
    if isinstance(default_renderers, list):
        default_renderers.append("rest_framework.renderers.BrowsableAPIRenderer")

# CORS Configuration
CORS_ALLOWED_ORIGINS_RAW = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Redis and Ephemeral Cache Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit

# Structured Development Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "onehopz": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
