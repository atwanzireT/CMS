from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    MyLoginView, users_list, user_create, user_edit, user_edit_me,
    user_access_edit, groups_list, group_create, group_access_edit,
)

app_name = "accounts"

urlpatterns = [
    # auth
    path("login/",  MyLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # users
    path("users/", users_list, name="users_list"),
    path("users/create/", user_create, name="user_create"),
    path("users/<int:user_id>/edit/", user_edit, name="user_edit"),
    path("users/<int:user_id>/access/", user_access_edit, name="user_access_edit"),
    path("profile/", user_edit_me, name="my_profile"),

    # groups
    path("groups/", groups_list, name="groups_list"),
    path("groups/create/", group_create, name="group_create"),
    path("groups/<int:group_id>/access/", group_access_edit, name="group_access_edit"),
]
