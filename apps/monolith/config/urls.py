from django.contrib import admin
from django.urls import include, path

from apps.monolith.catalog.views import CompanyLocationList, LocationDetail

from . import health, session_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("health/live", health.live),
    path("health/ready", health.ready),
    path("api/v1/auth/csrf", session_views.csrf_token, name="auth-csrf"),
    path("api/v1/auth/login", session_views.sign_in, name="auth-login"),
    path("api/v1/auth/logout", session_views.sign_out, name="auth-logout"),
    path(
        "api/v1/companies/<int:company_id>/locations",
        CompanyLocationList.as_view(),
        name="company-locations",
    ),
    path("api/v1/locations/<int:pk>", LocationDetail.as_view(), name="location-detail"),
]
