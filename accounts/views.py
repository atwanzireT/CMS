# accounts/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import (
    CustomUserChangeForm,
    CustomUserCreationForm,
    GroupAccessForm,
    GroupCreateForm,
    TailwindAuthenticationForm,
    UserAccessForm,
)

User = get_user_model()

# ---------- Auth ----------

class MyLoginView(LoginView):
    """
    Tailwind-styled login using our TailwindAuthenticationForm.
    Template: templates/registration/login.html
    """
    form_class = TailwindAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


# ---------- USERS ----------

@login_required
def users_list(request: HttpRequest) -> HttpResponse:
    """Simple user directory with search + pagination."""
    q = request.GET.get("q", "").strip()
    qs = User.objects.all().order_by("-id")
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page = request.GET.get("page")
    users = paginator.get_page(page)
    return render(request, "accounts/users_list.html", {"users": users, "q": q})


@login_required
def user_access_edit(request: HttpRequest, user_id: int) -> HttpResponse:
    """
    Toggle per-user access_* permissions via checkboxes discovered by the form.
    """
    target = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = UserAccessForm(request.POST, user_instance=target)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated access permissions for {target}.")
            return redirect(reverse("accounts:user_access_edit", args=[target.pk]))
    else:
        form = UserAccessForm(user_instance=target)
    return render(request, "accounts/user_access_edit.html", {"form": form, "target": target})


@login_required
def user_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User {user.username} created.")
            return redirect(reverse("accounts:users_list"))
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/user_form.html", {"form": form, "mode": "create"})


@login_required
def user_edit(request: HttpRequest, user_id: int) -> HttpResponse:
    target = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, request.FILES, instance=target)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {target.username} updated.")
            return redirect(reverse("accounts:users_list"))
    else:
        form = CustomUserChangeForm(instance=target)
    return render(request, "accounts/user_form.html", {"form": form, "mode": "edit", "target": target})


@login_required
def user_edit_me(request: HttpRequest) -> HttpResponse:
    """
    No-arg route to edit your own profile; useful for nav link { % url 'accounts:my_profile' % }.
    """
    return user_edit(request, request.user.id)


# ---------- GROUPS ----------

@login_required
def groups_list(request: HttpRequest) -> HttpResponse:
    """List groups with quick search."""
    q = request.GET.get("q", "").strip()
    qs = Group.objects.all().order_by("name")
    if q:
        qs = qs.filter(name__icontains=q)

    paginator = Paginator(qs, 30)
    page = request.GET.get("page")
    groups = paginator.get_page(page)
    return render(request, "accounts/groups_list.html", {"groups": groups, "q": q})


@login_required
def group_create(request: HttpRequest) -> HttpResponse:
    """
    Create a group and assign any selected access_* permissions.
    """
    if request.method == "POST":
        form = GroupCreateForm(request.POST)
        if form.is_valid():
            group = form.save()
            messages.success(request, f"Group '{group.name}' created.")
            return redirect(reverse("accounts:groups_list"))
    else:
        form = GroupCreateForm()
    return render(request, "accounts/group_create.html", {"form": form})


@login_required
def group_access_edit(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Toggle access_* permissions for an existing group.
    """
    group = get_object_or_404(Group, pk=group_id)
    if request.method == "POST":
        form = GroupAccessForm(request.POST, group_instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated access permissions for '{group.name}'.")
            return redirect(reverse("accounts:group_access_edit", args=[group.pk]))
    else:
        form = GroupAccessForm(group_instance=group)
    return render(request, "accounts/group_access_edit.html", {"form": form, "group": group})
