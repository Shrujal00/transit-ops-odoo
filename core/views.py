from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.db.models import Count, Q
from django.db import transaction
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from .models import Vehicle, Driver, Trip, MaintenanceLog, FuelLog, Expense, AuditLog

# Custom Mixins for RBAC View Guarding
class FleetManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Fleet Manager').exists()

class StaffOnlyRequiredMixin(UserPassesTestMixin):
    """Allows Fleet Manager, Safety Officer, Financial Analyst (not Drivers)"""
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return (self.request.user.is_superuser or 
                self.request.user.groups.filter(name__in=['Fleet Manager', 'Safety Officer', 'Financial Analyst']).exists())

class SafetyOfficerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return (self.request.user.is_superuser or 
                self.request.user.groups.filter(name__in=['Fleet Manager', 'Safety Officer']).exists())

class DriverSelfOrStaffRequiredMixin(UserPassesTestMixin):
    """Allows Driver to view their own profile, staff to view any"""
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        user = self.request.user
        if user.is_superuser or user.groups.filter(name__in=['Fleet Manager', 'Safety Officer', 'Financial Analyst']).exists():
            return True
        if user.groups.filter(name='Driver').exists():
            driver_obj = self.get_object()
            return hasattr(user, 'driver_profile') and user.driver_profile.pk == driver_obj.pk
        return False


# Dashboard View
@login_required
def dashboard_view(request):
    total_vehicles = Vehicle.objects.count()
    available_vehicles = Vehicle.objects.filter(status='Available').count()
    on_trip_vehicles = Vehicle.objects.filter(status='On Trip').count()
    in_shop_vehicles = Vehicle.objects.filter(status='In Shop').count()
    
    total_drivers = Driver.objects.count()
    available_drivers = Driver.objects.filter(status='Available').count()
    on_trip_drivers = Driver.objects.filter(status='On Trip').count()
    
    active_trips = Trip.objects.filter(status='Ongoing').count()
    
    # Audit logs for chatter (staff only)
    is_staff = request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Safety Officer', 'Financial Analyst']).exists()
    
    if is_staff:
        recent_logs = AuditLog.objects.all()[:10]
    else:
        recent_logs = AuditLog.objects.none()

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
        'is_staff': is_staff,
    }
    return render(request, 'core/dashboard.html', context)


# Vehicle Views
class VehicleListView(LoginRequiredMixin, StaffOnlyRequiredMixin, ListView):
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

class VehicleDetailView(LoginRequiredMixin, StaffOnlyRequiredMixin, DetailView):
    model = Vehicle
    template_name = 'core/vehicle_detail.html'
    context_object_name = 'vehicle'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vehicle = self.get_object()
        
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

class VehicleCreateView(LoginRequiredMixin, FleetManagerRequiredMixin, CreateView):
    model = Vehicle
    fields = ['registration_number', 'make', 'model', 'year', 'capacity_kg', 'acquisition_cost', 'status']
    template_name = 'core/vehicle_form.html'
    success_url = reverse_lazy('vehicle_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            new_status=self.object.status,
            details=f"Vehicle {self.object.registration_number} created in system."
        )
        return response

class VehicleUpdateView(LoginRequiredMixin, FleetManagerRequiredMixin, UpdateView):
    model = Vehicle
    fields = ['registration_number', 'make', 'model', 'year', 'capacity_kg', 'acquisition_cost', 'status']
    template_name = 'core/vehicle_form.html'

    def get_success_url(self):
        return reverse_lazy('vehicle_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        original = Vehicle.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        
        if original.status != self.object.status:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self.object)
            AuditLog.objects.create(
                user=self.request.user,
                content_type=ct,
                object_id=self.object.id,
                action='Status Change',
                old_status=original.status,
                new_status=self.object.status,
                details=f"Vehicle updated. Registration: {self.object.registration_number}"
            )
        return response

class VehicleDeleteView(LoginRequiredMixin, FleetManagerRequiredMixin, DeleteView):
    model = Vehicle
    template_name = 'core/vehicle_confirm_delete.html'
    success_url = reverse_lazy('vehicle_list')


# Driver Views
class DriverListView(LoginRequiredMixin, StaffOnlyRequiredMixin, ListView):
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

class DriverDetailView(LoginRequiredMixin, DriverSelfOrStaffRequiredMixin, DetailView):
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

class DriverCreateView(LoginRequiredMixin, FleetManagerRequiredMixin, CreateView):
    model = Driver
    fields = ['name', 'license_number', 'license_expiry', 'status', 'user']
    template_name = 'core/driver_form.html'
    success_url = reverse_lazy('driver_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            new_status=self.object.status,
            details=f"Driver {self.object.name} registered in system."
        )
        return response

class DriverUpdateView(LoginRequiredMixin, FleetManagerRequiredMixin, UpdateView):
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
                user=self.request.user,
                content_type=ct,
                object_id=self.object.id,
                action='Status Change',
                old_status=original.status,
                new_status=self.object.status,
                details=f"Driver {self.object.name} status updated."
            )
        return response

class DriverDeleteView(LoginRequiredMixin, FleetManagerRequiredMixin, DeleteView):
    model = Driver
    template_name = 'core/driver_confirm_delete.html'
    success_url = reverse_lazy('driver_list')


# Trip Views
class TripListView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = 'core/trip_list.html'
    context_object_name = 'trips'

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # If driver, only show their own trips
        if user.groups.filter(name='Driver').exists() and hasattr(user, 'driver_profile'):
            queryset = queryset.filter(driver=user.driver_profile)
        elif user.groups.filter(name='Driver').exists():
            queryset = queryset.none()
            
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Trip.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        return context

class TripDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Trip
    template_name = 'core/trip_detail.html'
    context_object_name = 'trip'

    def test_func(self):
        user = self.request.user
        if user.is_superuser or user.groups.filter(name__in=['Fleet Manager', 'Safety Officer', 'Financial Analyst']).exists():
            return True
        if user.groups.filter(name='Driver').exists():
            trip = self.get_object()
            return hasattr(user, 'driver_profile') and user.driver_profile == trip.driver
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trip = self.get_object()
        from django.contrib.contenttypes.models import ContentType
        trip_ct = ContentType.objects.get_for_model(Trip)
        
        context['audit_logs'] = AuditLog.objects.filter(
            content_type=trip_ct,
            object_id=trip.id
        )
        return context

class TripCreateView(LoginRequiredMixin, FleetManagerRequiredMixin, CreateView):
    model = Trip
    fields = ['source', 'destination', 'vehicle', 'driver', 'cargo_weight', 'revenue', 'scheduled_date']
    template_name = 'core/trip_form.html'
    success_url = reverse_lazy('trip_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            new_status=self.object.status,
            details=f"Trip from {self.object.source} to {self.object.destination} scheduled."
        )
        return response

class TripUpdateView(LoginRequiredMixin, FleetManagerRequiredMixin, UpdateView):
    model = Trip
    fields = ['source', 'destination', 'vehicle', 'driver', 'cargo_weight', 'revenue', 'scheduled_date', 'status']
    template_name = 'core/trip_form.html'

    def get_success_url(self):
        return reverse_lazy('trip_detail', kwargs={'pk': self.object.pk})

class TripDeleteView(LoginRequiredMixin, FleetManagerRequiredMixin, DeleteView):
    model = Trip
    template_name = 'core/trip_confirm_delete.html'
    success_url = reverse_lazy('trip_list')


# Dispatch State Machine Endpoints
@login_required
def trip_dispatch_view(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    
    if not (request.user.is_superuser or request.user.groups.filter(name='Fleet Manager').exists()):
        raise PermissionDenied("Only Fleet Managers can dispatch trips.")
        
    try:
        with transaction.atomic():
            # Apply row-level locks
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status != 'Draft':
                raise ValidationError("Only draft trips can be dispatched.")
                
            trip.status = 'Ongoing'
            # Trigger model clean checks (license validity, statuses, capacity)
            trip.full_clean()
            trip.save()
            
            # Transition vehicle and driver
            vehicle.status = 'On Trip'
            vehicle.save(update_fields=['status'])
            
            driver.status = 'On Trip'
            driver.save(update_fields=['status'])
            
            # Audit log
            from django.contrib.contenttypes.models import ContentType
            trip_ct = ContentType.objects.get_for_model(Trip)
            AuditLog.objects.create(
                user=request.user,
                content_type=trip_ct,
                object_id=trip.id,
                action='Dispatch',
                old_status='Draft',
                new_status='Ongoing',
                details=f"Trip dispatched. Vehicle: {vehicle.registration_number}, Driver: {driver.name}"
            )
            messages.success(request, f"Trip {trip.id} dispatched successfully!")
    except ValidationError as e:
        # Extract direct error message
        err_msg = e.message_dict if hasattr(e, 'message_dict') else str(e)
        messages.error(request, f"Dispatch failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Dispatch failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)

@login_required
def trip_complete_view(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    
    is_manager = request.user.is_superuser or request.user.groups.filter(name='Fleet Manager').exists()
    is_driver = hasattr(request.user, 'driver_profile') and request.user.driver_profile == trip.driver
    
    if not (is_manager or is_driver):
        raise PermissionDenied("You do not have permission to complete this trip.")
        
    try:
        with transaction.atomic():
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status != 'Ongoing':
                raise ValidationError("Only ongoing trips can be completed.")
                
            trip.status = 'Completed'
            trip.end_time = timezone.now()
            trip.save(update_fields=['status', 'end_time'])
            
            # Revert states to Available
            vehicle.status = 'Available'
            vehicle.save(update_fields=['status'])
            
            driver.status = 'Available'
            driver.save(update_fields=['status'])
            
            # Audit log
            from django.contrib.contenttypes.models import ContentType
            trip_ct = ContentType.objects.get_for_model(Trip)
            AuditLog.objects.create(
                user=request.user,
                content_type=trip_ct,
                object_id=trip.id,
                action='Complete',
                old_status='Ongoing',
                new_status='Completed',
                details=f"Trip completed."
            )
            messages.success(request, f"Trip {trip.id} completed successfully!")
    except Exception as e:
        messages.error(request, f"Completion failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)

@login_required
def trip_cancel_view(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    
    if not (request.user.is_superuser or request.user.groups.filter(name='Fleet Manager').exists()):
        raise PermissionDenied("Only Fleet Managers can cancel trips.")
        
    try:
        with transaction.atomic():
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status not in ['Draft', 'Ongoing']:
                raise ValidationError("Only draft or ongoing trips can be cancelled.")
                
            old_status = trip.status
            trip.status = 'Cancelled'
            trip.save(update_fields=['status'])
            
            # Revert states to Available
            vehicle.status = 'Available'
            vehicle.save(update_fields=['status'])
            
            driver.status = 'Available'
            driver.save(update_fields=['status'])
            
            # Audit log
            from django.contrib.contenttypes.models import ContentType
            trip_ct = ContentType.objects.get_for_model(Trip)
            AuditLog.objects.create(
                user=request.user,
                content_type=trip_ct,
                object_id=trip.id,
                action='Cancel',
                old_status=old_status,
                new_status='Cancelled',
                details=f"Trip cancelled."
            )
            messages.success(request, f"Trip {trip.id} has been cancelled.")
    except Exception as e:
        messages.error(request, f"Cancellation failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)


# Maintenance Views
class MaintenanceLogListView(LoginRequiredMixin, StaffOnlyRequiredMixin, ListView):
    model = MaintenanceLog
    template_name = 'core/maintenance_list.html'
    context_object_name = 'maintenance_logs'

class MaintenanceLogCreateView(LoginRequiredMixin, SafetyOfficerRequiredMixin, CreateView):
    model = MaintenanceLog
    fields = ['vehicle', 'description', 'cost', 'start_date', 'end_date', 'status']
    template_name = 'core/maintenance_form.html'
    success_url = reverse_lazy('maintenance_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self.object)
        AuditLog.objects.create(
            user=self.request.user,
            content_type=ct,
            object_id=self.object.id,
            action='Created',
            details=f"Maintenance log logged for {self.object.vehicle.registration_number}."
        )
        return response

class MaintenanceLogUpdateView(LoginRequiredMixin, SafetyOfficerRequiredMixin, UpdateView):
    model = MaintenanceLog
    fields = ['vehicle', 'description', 'cost', 'start_date', 'end_date', 'status']
    template_name = 'core/maintenance_form.html'
    success_url = reverse_lazy('maintenance_list')
