from django.urls import path

from roster import views

urlpatterns = [
    path("members/", views.member_list, name="member-list"),
    # "new/" comes before "<int:pk>/" so it is never read as a member id.
    path("members/new/", views.member_add, name="member-add"),
    path("members/<int:pk>/", views.member_detail, name="member-detail"),
    path("members/<int:pk>/edit/", views.member_edit, name="member-edit"),
    path("members/<int:pk>/status-history/", views.member_status_history, name="member-status-history"),
    path("members/<int:pk>/status/", views.member_status, name="member-status"),
]
