import os

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "monolith"]
ROOT_URLCONF = "apps.monolith.config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.monolith.catalog.apps.CatalogConfig",
]

# REST_FRAMEWORK = {
#     "DEFAULT_AUTHENTICATION_CLASSES": [
#         "rest_framework.authentication.SessionAuthentication",
#         "rest_framework.authentication.BasicAuthentication",
#     ],
# }

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "/static/"

TRACKER_ENABLE_DEV_WHOAMI = os.getenv("TRACKER_ENABLE_DEV_WHOAMI") == "1"
TRACKER_DEV_SIGNING_KEY = os.getenv("TRACKER_DEV_SIGNING_KEY", "")
TRACKER_BASE_URL = os.getenv("TRACKER_BASE_URL", "http://tracker:8000")
