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
    path("members/<int:pk>/section/", views.member_section, name="member-section"),
    path("members/<int:pk>/praise-team/", views.member_praise_team, name="member-praise-team"),
    path("members/<int:pk>/history/", views.member_history, name="member-history"),
    path("events/", views.event_list, name="event-list"),
    path("events/past/", views.event_past, name="event-past"),
    path("events/new/", views.event_add, name="event-add"),
    path("events/<int:pk>/cancel/", views.event_cancel, name="event-cancel"),
    path("events/create-upcoming/", views.events_create_upcoming, name="events-create-upcoming"),
]
