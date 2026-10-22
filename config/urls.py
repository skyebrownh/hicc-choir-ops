from django.contrib import admin
from django.urls import path

from config import views

urlpatterns = [
    path("health/", views.health),
    path("health/db/", views.health_db),
    path("admin/", admin.site.urls),
]
