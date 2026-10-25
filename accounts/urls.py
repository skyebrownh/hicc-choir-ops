from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.home, name="home"),
    path("week/", views.week_ahead, name="week-ahead"),
    path("attendance/", views.attendance_home, name="attendance-home"),
    path("accounts/", views.account_list, name="account-list"),
    # "new/" comes before any "<int:pk>" route so it is never read as an account id.
    path("accounts/new/", views.account_add, name="account-add"),
    path("signout/", views.sign_out, name="sign-out"),
    path("signin/", views.request_code, name="request-code"),
    path("signin/code/", views.enter_code, name="enter-code"),
]
