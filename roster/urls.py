from django.urls import path

from roster import views

urlpatterns = [
    # "new/" comes before "<int:pk>/" so it is never read as a member id.
    path("members/new/", views.member_add, name="member-add"),
    path("members/<int:pk>/", views.member_detail, name="member-detail"),
]
