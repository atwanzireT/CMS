from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.http.response import HttpResponseRedirect
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.urls import reverse_lazy
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm
from .models import UserActivity
from django.views.generic import ListView
from django.views import View


# Create your views here.
def login(request):
    return render(request, 'login.html', {})

def logout_func(request):
    logout(request)
    return HttpResponseRedirect('/accounts/login/')

def logout_page(request):
    return render(request, 'logout_user.html')


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/registration.html', {'form': form})

class UserActivityListView(ListView):
    model = UserActivity
    template_name = 'user_activity_list.html'
    context_object_name = 'activities'
    paginate_by = 20
    page_title = 'User Activities'
    ordering = ['-timestamp']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(user=self.request.user)
        return queryset