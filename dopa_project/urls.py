from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('cases:dashboard')),
    path('', include('cases.urls')),
    path('', include('collaboration.urls')),
    path('accounts/', include('accounts.urls')),
]
