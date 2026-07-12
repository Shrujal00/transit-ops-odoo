from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.db.models import Count, Q
from django.utils import timezone
from .models import Vehicle, Driver, Trip, MaintenanceLog, FuelLog, Expense, AuditLog

# Dashboard View
def dashboard_view(request):
    total_vehicles = Vehicle.objects.count()
    available_vehicles = Vehicle.objects.filter(status='Available').count()
    on_trip_vehicles = Vehicle.objects.filter(status='On Trip').count()
    in_shop_vehicles = Vehicle.objects.filter(status='In Shop').count()
    
    total_drivers = Driver.objects.count()
    available_drivers = Driver.objects.filter(status='Available').count()
    on_trip_drivers = Driver.objects.filter(status='On Trip').count()
    
    active_trips = Trip.objects.filter(status='Ongoing').count()
    
    # Audit logs for the chatter feed
    recent_logs = AuditLog.objects.all()[:10]

    context = {
        'total_vehicles': total_vehicles,
        'available_vehicles': available_vehicles,
        'on_trip_vehicles': on_trip_vehicles,
        'in_shop_vehicles': in_shop_vehicles,
        'total_drivers': total_drivers,
        'available_drivers': available_drivers,
        'on_trip_drivers': on_trip_drivers,
        'active_trips': active_trips,
        'recent_logs': recent_logs,
    }
    return render(request, 'core/dashboard.html', context)

# Vehicle Views
class VehicleListView(ListView):
    model = Vehicle
    template_name = 'core/vehicle_list.html'
    context_object_name = 'vehicles'

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.GET.get('status')
        search_query = self.request.GET.get('q')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if search_query:
            queryset = queryset.filter(
                Q(registration_number__icontains=search_query) |
                Q(make__icontains=search_query) |
                Q(model__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Vehicle.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context

class VehicleDetailView(DetailView):
    model = Vehicle
    template_name = 'core/vehicle_detail.html'
    context_object_name = 'vehicle'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vehicle = self.get_object()
        
        # Get content type for generic relation
        from django.contrib.contenttypes.models import ContentType
        vehicle_ct = ContentType.objects.get_for_model(Vehicle)
        
        context['audit_logs'] = AuditLog.objects.filter(
            content_type=vehicle_ct,
            object_id=vehicle.id
        )
        context['maintenance_logs'] = vehicle.maintenance_logs.all().order_by('-start_date')
        context['fuel_logs'] = vehicle.fuel_logs.all().order_by('-date')
        context['expenses'] = vehicle.expenses.all().order_by('-date')
        context['trips'] = vehicle.trips.all().order_by('-scheduled_date')
        return context

class VehicleCreateView(CreateView):
    model = Vehicle
    fields = ['registration_number', 'make', 'model', 'year', 'capacity_kg', 'acquisition_cost', 'status']
    template_name = 'core/vehicle_form.html'
    success_url = reverse_lazy('vehicle_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        # Create an audit log entry
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            new_status=self.object.status,
            details=f"Vehicle {self.object.registration_number} created in system."
        )
        return response

class VehicleUpdateView(UpdateView):
    model = Vehicle
    fields = ['registration_number', 'make', 'model', 'year', 'capacity_kg', 'acquisition_cost', 'status']
    template_name = 'core/vehicle_form.html'

    def get_success_url(self):
        return reverse_lazy('vehicle_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        # Fetch original object before save
        original = Vehicle.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        
        # Log status change if status modified
        if original.status != self.object.status:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self.object)
            AuditLog.objects.create(
                user=self.request.user if self.request.user.is_authenticated else None,
                content_type=ct,
                object_id=self.object.id,
                action='Status Change',
                old_status=original.status,
                new_status=self.object.status,
                details=f"Vehicle updated. Registration: {self.object.registration_number}"
            )
        return response

class VehicleDeleteView(DeleteView):
    model = Vehicle
    template_name = 'core/vehicle_confirm_delete.html'
    success_url = reverse_lazy('vehicle_list')


# Driver Views
class DriverListView(ListView):
    model = Driver
    template_name = 'core/driver_list.html'
    context_object_name = 'drivers'

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.GET.get('status')
        search_query = self.request.GET.get('q')

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(license_number__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Driver.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context

class DriverDetailView(DetailView):
    model = Driver
    template_name = 'core/driver_detail.html'
    context_object_name = 'driver'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        driver = self.get_object()
        
        from django.contrib.contenttypes.models import ContentType
        driver_ct = ContentType.objects.get_for_model(Driver)
        
        context['audit_logs'] = AuditLog.objects.filter(
            content_type=driver_ct,
            object_id=driver.id
        )
        context['trips'] = driver.trips.all().order_by('-scheduled_date')
        return context

class DriverCreateView(CreateView):
    model = Driver
    fields = ['name', 'license_number', 'license_expiry', 'status', 'user']
    template_name = 'core/driver_form.html'
    success_url = reverse_lazy('driver_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            new_status=self.object.status,
            details=f"Driver {self.object.name} registered in system."
        )
        return response

class DriverUpdateView(UpdateView):
    model = Driver
    fields = ['name', 'license_number', 'license_expiry', 'status', 'user']
    template_name = 'core/driver_form.html'

    def get_success_url(self):
        return reverse_lazy('driver_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        original = Driver.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        
        if original.status != self.object.status:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self.object)
            AuditLog.objects.create(
                user=self.request.user if self.request.user.is_authenticated else None,
                content_type=ct,
                object_id=self.object.id,
                action='Status Change',
                old_status=original.status,
                new_status=self.object.status,
                details=f"Driver {self.object.name} status updated."
            )
        return response

class DriverDeleteView(DeleteView):
    model = Driver
    template_name = 'core/driver_confirm_delete.html'
    success_url = reverse_lazy('driver_list')


# View mappings for routing shortcuts
dashboard_view = dashboard_view
vehicle_list_view = VehicleListView.as_view()
vehicle_detail_view = VehicleDetailView.as_view()
vehicle_create_view = VehicleCreateView.as_view()
vehicle_update_view = VehicleUpdateView.as_view()
vehicle_delete_view = VehicleDeleteView.as_view()

driver_list_view = DriverListView.as_view()
driver_detail_view = DriverDetailView.as_view()
driver_create_view = DriverCreateView.as_view()
driver_update_view = DriverUpdateView.as_view()
driver_delete_view = DriverDeleteView.as_view()
