from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.home, name="home"),
    path("week/", views.week_ahead, name="week-ahead"),
    path("attendance/", views.attendance_home, name="attendance-home"),
    path("signin/", views.request_code, name="request-code"),
    path("signin/code/", views.enter_code, name="enter-code"),
]
