from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from config import views

urlpatterns = [
    path("health/", views.health),
    path("health/db/", views.health_db),
    # AC-1: there are no passwords, so the admin's login form is replaced by ours.
    path("admin/login/", RedirectView.as_view(pattern_name="request-code")),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("roster.urls")),
]
