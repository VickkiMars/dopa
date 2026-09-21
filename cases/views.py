from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin


class DashboardView(LoginRequiredMixin, View):
    template_name = 'cases/dashboard.html'

    def get(self, request):
        user = request.user
        context = {
            'user': user,
            'role_display': user.get_role_display(),
            'is_primary_physician': user.is_primary_physician,
            'is_specialist': user.is_specialist,
            'cases': [],  # To be populated in Sprint 2
        }
        return render(request, self.template_name, context)
