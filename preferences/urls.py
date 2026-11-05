from django.urls import path
from django.contrib.auth import views as auth_views
from . import views


app_name = "preferences"

urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),


    path(
        "achievements/",
        views.achievements,
        name="achievements",
    ),
    
    
    path("signup/", views.signup, name="signup"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path("setup/", views.setup_preferences, name="setup"),
    path("profile/", views.profile, name="profile"),
    path("suggest/", views.suggest_activity, name="suggest"),

    path(
        "activity/<int:pk>/",
        views.activity_detail,
        name="activity",
    ),

path(
    "activity/<int:pk>/end/",
    views.end_activity,
    name="end",
),
    path(
        "activity/<int:pk>/start/",
        views.start_activity,
        name="start",
    ),

    path(
        "activity/<int:pk>/complete/",
        views.complete_activity,
        name="complete",
    ),
    path(
    "items/<int:pk>/edit/",
    views.item_edit,
    name="item_edit",
),

path(
    "items/<int:pk>/archive/",
    views.item_archive,
    name="item_archive",
),

path(
    "activity/<int:pk>/cancel/",
    views.cancel_activity,
    name="cancel",
),
path(
    "items/<int:pk>/delete/",
    views.item_delete,
    name="item_delete",
),
]