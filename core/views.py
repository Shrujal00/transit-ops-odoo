from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.db.models import Count, Q, Sum
from django.db import transaction
import datetime
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, Http404
from decimal import Decimal
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

class FinancialRequiredMixin(UserPassesTestMixin):
    """Allows Fleet Manager and Financial Analyst"""
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return (self.request.user.is_superuser or 
                self.request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists())

class DriverRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Driver').exists()

class SafetyOfficerOnlyRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Safety Officer').exists()

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
    pending_trips = Trip.objects.filter(status='Draft').count()
    drivers_on_duty = Driver.objects.filter(status='On Trip').count()
    
    if total_vehicles > 0:
        fleet_utilization = (on_trip_vehicles / total_vehicles) * 100
    else:
        fleet_utilization = 0.0
        
    # Cost breakdown for Chart.js
    total_fuel_cost = FuelLog.objects.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
    total_maint_cost = MaintenanceLog.objects.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
    total_expense_cost = Expense.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    cost_breakdown = {
        'Fuel': float(total_fuel_cost),
        'Maintenance': float(total_maint_cost),
        'Expenses': float(total_expense_cost)
    }
    
    # Fuel efficiency per vehicle for Chart.js
    efficiency_data = []
    for vehicle in Vehicle.objects.filter(status__in=['Available', 'On Trip', 'In Shop']):
        trip_qs = vehicle.trips.filter(status='Completed')
        total_distance = trip_qs.aggregate(total=Sum('planned_distance'))['total'] or 0
        total_fuel_consumed = trip_qs.aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00')
        total_fuel_logged = vehicle.fuel_logs.aggregate(total=Sum('liters'))['total'] or Decimal('0.00')
        
        total_fuel_consumed = Decimal(str(total_fuel_consumed))
        total_fuel_logged = Decimal(str(total_fuel_logged))
        
        eff_fuel = total_fuel_consumed if total_fuel_consumed > 0 else total_fuel_logged
        if eff_fuel > 0:
            eff = float(Decimal(str(total_distance)) / eff_fuel)
        else:
            eff = 0.0
        efficiency_data.append({
            'reg': vehicle.registration_number,
            'efficiency': round(eff, 2)
        })
    
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
        'pending_trips': pending_trips,
        'drivers_on_duty': drivers_on_duty,
        'fleet_utilization': fleet_utilization,
        'cost_breakdown': cost_breakdown,
        'efficiency_data': efficiency_data,
        'recent_logs': recent_logs,
        'is_staff': is_staff,
    }
    return render(request, 'core/dashboard.html', context)


# Vehicle Views
class VehicleListView(LoginRequiredMixin, StaffOnlyRequiredMixin, ListView):
    model = Vehicle
    template_name = 'core/vehicle_list.html'
    context_object_name = 'vehicles'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.GET.get('status')
        type_filter = self.request.GET.get('type')
        region_filter = self.request.GET.get('region')
        search_query = self.request.GET.get('q')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if type_filter:
            queryset = queryset.filter(type=type_filter)
        if region_filter:
            queryset = queryset.filter(region=region_filter)
        if search_query:
            queryset = queryset.filter(
                Q(registration_number__icontains=search_query) |
                Q(make__icontains=search_query) |
                Q(model__icontains=search_query)
            )
        return queryset.order_by('registration_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Vehicle.STATUS_CHOICES
        context['type_choices'] = Vehicle.TYPE_CHOICES
        context['region_choices'] = Vehicle.REGION_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        context['current_type'] = self.request.GET.get('type', '')
        context['current_region'] = self.request.GET.get('region', '')
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
    fields = ['registration_number', 'make', 'model', 'type', 'region', 'year', 'capacity_kg', 'odometer', 'acquisition_cost', 'status']
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
    fields = ['registration_number', 'make', 'model', 'type', 'region', 'year', 'capacity_kg', 'odometer', 'acquisition_cost', 'status']
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
    paginate_by = 15

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
        return queryset.order_by('name')

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

class DriverCreateView(LoginRequiredMixin, SafetyOfficerOnlyRequiredMixin, CreateView):
    model = Driver
    fields = ['name', 'license_number', 'license_category', 'license_expiry', 'contact_number', 'safety_score', 'status', 'user']
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

class DriverUpdateView(LoginRequiredMixin, SafetyOfficerOnlyRequiredMixin, UpdateView):
    model = Driver
    fields = ['name', 'license_number', 'license_category', 'license_expiry', 'contact_number', 'safety_score', 'status', 'user']
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

class DriverDeleteView(LoginRequiredMixin, SafetyOfficerOnlyRequiredMixin, DeleteView):
    model = Driver
    template_name = 'core/driver_confirm_delete.html'
    success_url = reverse_lazy('driver_list')


# Trip Views
class TripListView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = 'core/trip_list.html'
    context_object_name = 'trips'
    paginate_by = 15

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
        return queryset.order_by('-scheduled_date')

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

class TripCreateView(LoginRequiredMixin, DriverRequiredMixin, CreateView):
    model = Trip
    fields = ['source', 'destination', 'vehicle', 'driver', 'cargo_weight', 'planned_distance', 'revenue', 'scheduled_date']
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

class TripUpdateView(LoginRequiredMixin, DriverRequiredMixin, UpdateView):
    model = Trip
    fields = ['source', 'destination', 'vehicle', 'driver', 'cargo_weight', 'planned_distance', 'revenue', 'scheduled_date', 'status']
    template_name = 'core/trip_form.html'

    def get_success_url(self):
        return reverse_lazy('trip_detail', kwargs={'pk': self.object.pk})

class TripDeleteView(LoginRequiredMixin, DriverRequiredMixin, DeleteView):
    model = Trip
    template_name = 'core/trip_confirm_delete.html'
    success_url = reverse_lazy('trip_list')


# Dispatch State Machine Endpoints
@login_required
def trip_dispatch_view(request, pk):
    try:
        trip = get_object_or_404(Trip, pk=pk)
        
        if not (request.user.is_superuser or request.user.groups.filter(name='Driver').exists()):
            raise PermissionDenied("Only Drivers can dispatch trips.")
            
        with transaction.atomic():
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status != 'Draft':
                raise ValidationError("Only draft trips can be dispatched.")
                
            trip.status = 'Ongoing'
            trip.full_clean()
            trip.save()
            
            vehicle.status = 'On Trip'
            vehicle.save(update_fields=['status'])
            
            driver.status = 'On Trip'
            driver.save(update_fields=['status'])
            
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
    except Http404 as e:
        raise e
    except PermissionDenied as e:
        raise e
    except ValidationError as e:
        err_msg = e.message_dict if hasattr(e, 'message_dict') else str(e)
        messages.error(request, f"Dispatch failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Dispatch failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)

@login_required
def trip_complete_view(request, pk):
    try:
        trip = get_object_or_404(Trip, pk=pk)
        
        is_driver = request.user.is_superuser or (request.user.groups.filter(name='Driver').exists() and hasattr(request.user, 'driver_profile') and request.user.driver_profile == trip.driver)
        
        if not is_driver:
            raise PermissionDenied("Only the assigned Driver can complete this trip.")
            
        with transaction.atomic():
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status != 'Ongoing':
                raise ValidationError("Only ongoing trips can be completed.")
                
            end_odo_str = request.POST.get('end_odometer')
            fuel_str = request.POST.get('fuel_consumed')
            
            if not end_odo_str or not fuel_str:
                raise ValidationError("Final odometer and fuel consumed are required to complete this trip.")
                
            try:
                end_odo = int(end_odo_str)
                fuel = Decimal(fuel_str)
            except ValueError:
                raise ValidationError("Odometer and fuel consumed must be valid numeric values.")
                
            trip.status = 'Completed'
            trip.end_time = timezone.now()
            trip.end_odometer = end_odo
            trip.fuel_consumed = fuel
            trip.full_clean()
            trip.save()
            
            # Update vehicle status and odometer!
            vehicle.status = 'Available'
            vehicle.odometer = end_odo
            vehicle.save(update_fields=['status', 'odometer'])
            
            driver.status = 'Available'
            driver.save(update_fields=['status'])
            
            from django.contrib.contenttypes.models import ContentType
            trip_ct = ContentType.objects.get_for_model(Trip)
            AuditLog.objects.create(
                user=request.user,
                content_type=trip_ct,
                object_id=trip.id,
                action='Complete',
                old_status='Ongoing',
                new_status='Completed',
                details=f"Trip completed. Final Odometer: {end_odo}, Fuel Consumed: {fuel} L."
            )
            messages.success(request, f"Trip {trip.id} completed successfully!")
    except Http404 as e:
        raise e
    except PermissionDenied as e:
        raise e
    except ValidationError as e:
        err_msg = e.message_dict if hasattr(e, 'message_dict') else str(e)
        messages.error(request, f"Completion failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Completion failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)

@login_required
def trip_cancel_view(request, pk):
    try:
        trip = get_object_or_404(Trip, pk=pk)
        
        if not (request.user.is_superuser or request.user.groups.filter(name='Driver').exists()):
            raise PermissionDenied("Only Drivers can cancel trips.")
            
        with transaction.atomic():
            trip = Trip.objects.select_for_update().get(pk=pk)
            vehicle = Vehicle.objects.select_for_update().get(pk=trip.vehicle.pk)
            driver = Driver.objects.select_for_update().get(pk=trip.driver.pk)
            
            if trip.status not in ['Draft', 'Ongoing']:
                raise ValidationError("Only draft or ongoing trips can be cancelled.")
                
            old_status = trip.status
            trip.status = 'Cancelled'
            trip.save(update_fields=['status'])
            
            vehicle.status = 'Available'
            vehicle.save(update_fields=['status'])
            
            driver.status = 'Available'
            driver.save(update_fields=['status'])
            
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
    except Http404 as e:
        raise e
    except PermissionDenied as e:
        raise e
    except ValidationError as e:
        err_msg = e.message_dict if hasattr(e, 'message_dict') else str(e)
        messages.error(request, f"Cancellation failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Cancellation failed: {str(e)}")
        
    return redirect('trip_detail', pk=pk)


# Maintenance Views
class MaintenanceLogListView(LoginRequiredMixin, StaffOnlyRequiredMixin, ListView):
    model = MaintenanceLog
    template_name = 'core/maintenance_list.html'
    context_object_name = 'maintenance_logs'
    paginate_by = 15

    def get_queryset(self):
        return super().get_queryset().order_by('-start_date')

class MaintenanceLogCreateView(LoginRequiredMixin, FleetManagerRequiredMixin, CreateView):
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

class MaintenanceLogUpdateView(LoginRequiredMixin, FleetManagerRequiredMixin, UpdateView):
    model = MaintenanceLog
    fields = ['vehicle', 'description', 'cost', 'start_date', 'end_date', 'status']
    template_name = 'core/maintenance_form.html'
    success_url = reverse_lazy('maintenance_list')


# Finance & Analytics Views
def _get_finance_data(start_date_str=None, end_date_str=None):
    """Helper function to calculate operational costs and ROI per vehicle and fleet-wide"""
    start_date = None
    end_date = None
    
    if start_date_str:
        try:
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    vehicles_data = []
    
    # Fleet-wide aggregations
    fleet_revenue = Decimal('0.00')
    fleet_maintenance = Decimal('0.00')
    fleet_fuel = Decimal('0.00')
    fleet_acquisition = Decimal('0.00')
    
    vehicles = Vehicle.objects.all()
    for vehicle in vehicles:
        # Sums
        fuel_qs = vehicle.fuel_logs.all()
        maint_qs = vehicle.maintenance_logs.all()
        trip_qs = vehicle.trips.filter(status='Completed')
        
        if start_date:
            fuel_qs = fuel_qs.filter(date__gte=start_date)
            maint_qs = maint_qs.filter(start_date__gte=start_date)
            trip_qs = trip_qs.filter(scheduled_date__gte=start_date)
        if end_date:
            fuel_qs = fuel_qs.filter(date__lte=end_date)
            maint_qs = maint_qs.filter(start_date__lte=end_date)
            trip_qs = trip_qs.filter(scheduled_date__lte=end_date)
            
        fuel_cost = fuel_qs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        maint_cost = maint_qs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        revenue = trip_qs.aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
        
        # Odometer and Fuel Efficiency calculation
        total_distance = trip_qs.aggregate(total=Sum('planned_distance'))['total'] or 0
        total_fuel_consumed = trip_qs.aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00')
        total_fuel_logged = fuel_qs.aggregate(total=Sum('liters'))['total'] or Decimal('0.00')
        
        fuel_cost = Decimal(str(fuel_cost))
        maint_cost = Decimal(str(maint_cost))
        revenue = Decimal(str(revenue))
        acq_cost = Decimal(str(vehicle.acquisition_cost))
        total_fuel_consumed = Decimal(str(total_fuel_consumed))
        total_fuel_logged = Decimal(str(total_fuel_logged))
        
        op_cost = fuel_cost + maint_cost
        
        if acq_cost > 0:
            roi = (revenue - op_cost) / acq_cost
        else:
            roi = Decimal('0.00')
            
        efficiency_fuel = total_fuel_consumed if total_fuel_consumed > 0 else total_fuel_logged
        if efficiency_fuel > 0:
            fuel_efficiency = Decimal(str(total_distance)) / efficiency_fuel
        else:
            fuel_efficiency = Decimal('0.00')
            
        # Add to fleet-wide totals
        fleet_revenue += revenue
        fleet_maintenance += maint_cost
        fleet_fuel += fuel_cost
        fleet_acquisition += acq_cost
        
        vehicles_data.append({
            'vehicle': vehicle,
            'revenue': revenue,
            'maintenance': maint_cost,
            'fuel': fuel_cost,
            'op_cost': op_cost,
            'roi': roi,
            'roi_percentage': roi * 100,
            'fuel_efficiency': fuel_efficiency,
            'total_distance': total_distance
        })
        
    fleet_op_cost = fleet_maintenance + fleet_fuel
    if fleet_acquisition > 0:
        fleet_roi = (fleet_revenue - fleet_op_cost) / fleet_acquisition
    else:
        fleet_roi = Decimal('0.00')
        
    # Fleet-wide fuel efficiency
    fleet_total_distance = sum(item['total_distance'] for item in vehicles_data)
    fleet_total_fuel_efficiency_base = sum(
        (item['vehicle'].trips.filter(status='Completed').aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00'))
        for item in vehicles_data
    )
    if fleet_total_fuel_efficiency_base == 0:
        fleet_total_fuel_efficiency_base = FuelLog.objects.all().aggregate(total=Sum('liters'))['total'] or Decimal('0.00')
        
    fleet_total_fuel_efficiency_base = Decimal(str(fleet_total_fuel_efficiency_base))
    if fleet_total_fuel_efficiency_base > 0:
        fleet_fuel_efficiency = Decimal(str(fleet_total_distance)) / fleet_total_fuel_efficiency_base
    else:
        fleet_fuel_efficiency = Decimal('0.00')
        
    return {
        'vehicles': vehicles_data,
        'fleet_revenue': fleet_revenue,
        'fleet_maintenance': fleet_maintenance,
        'fleet_fuel': fleet_fuel,
        'fleet_op_cost': fleet_op_cost,
        'fleet_acquisition': fleet_acquisition,
        'fleet_roi': fleet_roi,
        'fleet_roi_percentage': fleet_roi * 100,
        'fleet_fuel_efficiency': fleet_fuel_efficiency,
        'start_date': start_date_str or '',
        'end_date': end_date_str or ''
    }

class FinanceReportView(LoginRequiredMixin, FinancialRequiredMixin, TemplateView):
    template_name = 'core/finance_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        finance_data = _get_finance_data(start_date, end_date)
        context.update(finance_data)
        return context

class AnalyticsView(LoginRequiredMixin, FinancialRequiredMixin, TemplateView):
    template_name = 'core/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # 1. Weekly Revenue vs Cost Trend (W-7 to W-0)
        weekly_labels = []
        weekly_revenue = []
        weekly_cost = []
        for i in range(7, -1, -1):
            start = today - datetime.timedelta(days=(i+1)*7)
            end = today - datetime.timedelta(days=i*7)
            weekly_labels.append(f"W-{i}")
            
            # Revenue
            rev_val = Trip.objects.filter(
                scheduled_date__range=[start, end], status='Completed'
            ).aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
            weekly_revenue.append(float(rev_val))
            
            # Cost
            maint_val = MaintenanceLog.objects.filter(
                start_date__range=[start, end]
            ).aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
            fuel_val = FuelLog.objects.filter(
                date__range=[start, end]
            ).aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
            exp_val = Expense.objects.filter(
                date__range=[start, end]
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            total_c = maint_val + fuel_val + exp_val
            weekly_cost.append(float(total_c))

        # 2. Trip Analytics
        trip_counts = {
            'Completed': Trip.objects.filter(status='Completed').count(),
            'In Progress': Trip.objects.filter(status='Ongoing').count(),
            'Pending': Trip.objects.filter(status='Draft').count(),
            'Cancelled': Trip.objects.filter(status='Cancelled').count(),
        }

        # 3. Fuel Efficiency (Litres over time) for last 14 days
        fuel_labels = []
        fuel_liters = []
        for i in range(13, -1, -1):
            day = today - datetime.timedelta(days=i)
            fuel_labels.append(day.strftime('%m-%d'))
            liters = FuelLog.objects.filter(date=day).aggregate(total=Sum('liters'))['total'] or Decimal('0.00')
            fuel_liters.append(float(liters))

        # 4. Top Driver Radar (Safety vs Trips) - pick top 6 drivers
        top_drivers = Driver.objects.exclude(user__isnull=True).order_by('-safety_score')[:6]
        radar_labels = []
        radar_safety = []
        radar_trips = []
        for d in top_drivers:
            radar_labels.append(d.name.split()[0])
            radar_safety.append(d.safety_score)
            radar_trips.append(d.trips.filter(status='Completed').count())

        context.update({
            'weekly_labels': weekly_labels,
            'weekly_revenue': weekly_revenue,
            'weekly_cost': weekly_cost,
            'trip_counts': trip_counts,
            'fuel_labels': fuel_labels,
            'fuel_liters': fuel_liters,
            'radar_labels': radar_labels,
            'radar_safety': radar_safety,
            'radar_trips': radar_trips,
        })
        return context

@login_required
def finance_api_view(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists()):
        raise PermissionDenied("You do not have permission to access financial data APIs.")
        
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    data = _get_finance_data(start_date, end_date)
    
    # Serialize data for JSON
    serialized_vehicles = []
    for item in data['vehicles']:
        serialized_vehicles.append({
            'id': item['vehicle'].id,
            'registration_number': item['vehicle'].registration_number,
            'make': item['vehicle'].make,
            'model': item['vehicle'].model,
            'acquisition_cost': float(item['vehicle'].acquisition_cost),
            'revenue': float(item['revenue']),
            'maintenance': float(item['maintenance']),
            'fuel': float(item['fuel']),
            'op_cost': float(item['op_cost']),
            'roi': float(item['roi']),
            'roi_percentage': float(item['roi_percentage']),
            'fuel_efficiency': float(item['fuel_efficiency'])
        })
        
    response_data = {
        'fleet_revenue': float(data['fleet_revenue']),
        'fleet_maintenance': float(data['fleet_maintenance']),
        'fleet_fuel': float(data['fleet_fuel']),
        'fleet_op_cost': float(data['fleet_op_cost']),
        'fleet_acquisition': float(data['fleet_acquisition']),
        'fleet_roi': float(data['fleet_roi']),
        'fleet_roi_percentage': float(data['fleet_roi_percentage']),
        'fleet_fuel_efficiency': float(data['fleet_fuel_efficiency']),
        'vehicles': serialized_vehicles,
        'start_date': data['start_date'],
        'end_date': data['end_date']
    }
    
    return JsonResponse(response_data)


# Quick Actions (One-Click Operations)
from django.views.decorators.http import require_POST

@login_required
@require_POST
def vehicle_quick_maintenance(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='Fleet Manager').exists()):
        raise PermissionDenied("Only Fleet Managers can change maintenance status.")
    
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if vehicle.status != 'Available':
        messages.error(request, "Only available vehicles can be sent to maintenance.")
        return redirect('vehicle_list')
        
    with transaction.atomic():
        vehicle.status = 'In Shop'
        vehicle.save(update_fields=['status'])
        
        log = MaintenanceLog(
            vehicle=vehicle,
            description="Scheduled via Quick Action",
            cost=Decimal('0.00'),
            start_date=timezone.now().date(),
            status='In Progress'
        )
        log._bypass_date_validation = True
        log.save()
        
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Vehicle)
        AuditLog.objects.create(
            user=request.user,
            content_type=ct,
            object_id=vehicle.id,
            action='Status Change',
            old_status='Available',
            new_status='In Shop',
            details="Vehicle sent to maintenance via quick action."
        )
        messages.success(request, f"Vehicle {vehicle.registration_number} sent to maintenance.")
        
    return redirect('vehicle_list')

@login_required
@require_POST
def vehicle_quick_resolve_maintenance(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='Fleet Manager').exists()):
        raise PermissionDenied("Only Fleet Managers can change maintenance status.")
        
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if vehicle.status != 'In Shop':
        messages.error(request, "Only vehicles in shop can be returned to service.")
        return redirect('vehicle_list')
        
    with transaction.atomic():
        log = vehicle.maintenance_logs.exclude(status='Completed').first()
        if log:
            today = timezone.now().date()
            if log.start_date > today:
                log.start_date = today
            log.status = 'Completed'
            log.end_date = today
            log._bypass_date_validation = True
            log.save()
            
        vehicle.status = 'Available'
        vehicle.save(update_fields=['status'])
        
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Vehicle)
        AuditLog.objects.create(
            user=request.user,
            content_type=ct,
            object_id=vehicle.id,
            action='Status Change',
            old_status='In Shop',
            new_status='Available',
            details="Vehicle returned to service via quick action."
        )
        messages.success(request, f"Vehicle {vehicle.registration_number} returned to service.")
        
    return redirect('vehicle_list')

@login_required
@require_POST
def trip_quick_dispatch(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='Driver').exists()):
        raise PermissionDenied("Only Drivers can dispatch trips.")
        
    trip = get_object_or_404(Trip, pk=pk)
    if trip.status != 'Draft':
        messages.error(request, "Only draft trips can be dispatched.")
        return redirect('trip_list')
        
    with transaction.atomic():
        vehicle = trip.vehicle
        if vehicle.status != 'Available':
            vehicle.status = 'Available'
            vehicle.save(update_fields=['status'])
            
        driver = trip.driver
        if driver.status != 'Available':
            driver.status = 'Available'
            driver.save(update_fields=['status'])

        trip.status = 'Ongoing'
        trip._bypass_date_validation = True
        trip.save()
        
        vehicle.status = 'On Trip'
        vehicle.save(update_fields=['status'])
        
        driver.status = 'On Trip'
        driver.save(update_fields=['status'])
        
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Trip)
        AuditLog.objects.create(
            user=request.user,
            content_type=ct,
            object_id=trip.id,
            action='Dispatch',
            old_status='Draft',
            new_status='Ongoing',
            details="Trip dispatched via quick action."
        )
        messages.success(request, f"Trip {trip.id} dispatched successfully.")
        
    return redirect('trip_list')

@login_required
@require_POST
def trip_quick_complete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    is_driver = request.user.is_superuser or (request.user.groups.filter(name='Driver').exists() and hasattr(request.user, 'driver_profile') and request.user.driver_profile == trip.driver)
    
    if not is_driver:
        raise PermissionDenied("Only the assigned Driver can complete this trip.")
        
    if trip.status != 'Ongoing':
        messages.error(request, "Only ongoing trips can be completed.")
        return redirect('trip_list')
        
    with transaction.atomic():
        end_odo = trip.vehicle.odometer + trip.planned_distance
        fuel = Decimal(str(trip.planned_distance * 0.15))
        
        trip.status = 'Completed'
        trip.end_time = timezone.now()
        trip.end_odometer = end_odo
        trip.fuel_consumed = fuel
        trip._bypass_date_validation = True
        trip.save()
        
        vehicle = trip.vehicle
        vehicle.status = 'Available'
        vehicle.odometer = end_odo
        vehicle.save(update_fields=['status', 'odometer'])
        
        driver = trip.driver
        driver.status = 'Available'
        driver.save(update_fields=['status'])
        
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Trip)
        AuditLog.objects.create(
            user=request.user,
            content_type=ct,
            object_id=trip.id,
            action='Complete',
            old_status='Ongoing',
            new_status='Completed',
            details=f"Trip completed via quick action. Final Odo: {end_odo}, Fuel Consumed: {fuel} L."
        )
        messages.success(request, f"Trip {trip.id} completed successfully.")
        
    return redirect('trip_list')


# Reports & Exports View
class ReportsView(LoginRequiredMixin, FinancialRequiredMixin, TemplateView):
    template_name = 'core/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Vehicles performance data
        vehicles = Vehicle.objects.all()
        vehicles_report = []
        for v in vehicles[:100]: # limit to top 100 for display
            trips_count = v.trips.filter(status='Completed').count()
            rev = v.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
            fuel_c = v.fuel_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
            maint_c = v.maintenance_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
            exp_c = v.expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            total_cost = fuel_c + maint_c + exp_c
            profit = rev - total_cost
            roi = (profit / v.acquisition_cost * 100) if v.acquisition_cost > 0 else Decimal('0.00')
            
            vehicles_report.append({
                'registration_number': v.registration_number,
                'model': f"{v.make} {v.model}",
                'trips': trips_count,
                'revenue': rev,
                'cost': total_cost,
                'profit': profit,
                'roi': roi
            })
            
        # Drivers performance data
        drivers = Driver.objects.all()
        drivers_report = []
        for d in drivers[:100]: # limit to top 100 for display
            total_trips = d.trips.count()
            comp_trips = d.trips.filter(status='Completed').count()
            fuel = d.trips.filter(status='Completed').aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00')
            rev = d.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
            
            drivers_report.append({
                'name': d.name,
                'total_trips': total_trips,
                'completed_trips': comp_trips,
                'safety_score': d.safety_score,
                'fuel_consumed': fuel,
                'revenue': rev,
                'status': d.status
            })
            
        context.update({
            'vehicles_report': vehicles_report,
            'drivers_report': drivers_report,
        })
        return context


import csv
from django.http import HttpResponse

@login_required
def export_vehicles_csv(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists()):
        raise PermissionDenied()
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="vehicle_performance_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['REG', 'MODEL', 'TRIPS', 'REVENUE (INR)', 'COST (INR)', 'PROFIT (INR)', 'ROI (%)'])
    
    vehicles = Vehicle.objects.all()
    for v in vehicles:
        trips_count = v.trips.filter(status='Completed').count()
        rev = v.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
        fuel_c = v.fuel_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        maint_c = v.maintenance_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        exp_c = v.expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        total_cost = fuel_c + maint_c + exp_c
        profit = rev - total_cost
        roi = (profit / v.acquisition_cost * 100) if v.acquisition_cost > 0 else Decimal('0.00')
        
        writer.writerow([
            v.registration_number,
            f"{v.make} {v.model}",
            trips_count,
            float(rev),
            float(total_cost),
            float(profit),
            f"{float(roi):.2f}%"
        ])
    return response

@login_required
def export_drivers_csv(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists()):
        raise PermissionDenied()
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="driver_performance_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['DRIVER NAME', 'TOTAL TRIPS', 'COMPLETED TRIPS', 'SAFETY SCORE', 'FUEL CONSUMED (L)', 'TOTAL REVENUE (INR)', 'STATUS'])
    
    drivers = Driver.objects.all()
    for d in drivers:
        total_trips = d.trips.count()
        comp_trips = d.trips.filter(status='Completed').count()
        fuel = d.trips.filter(status='Completed').aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00')
        rev = d.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
        
        writer.writerow([
            d.name,
            total_trips,
            comp_trips,
            d.safety_score,
            float(fuel),
            float(rev),
            d.status
        ])
    return response

@login_required
def export_vehicles_pdf(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists()):
        raise PermissionDenied()
        
    vehicles = Vehicle.objects.all()
    vehicles_report = []
    for v in vehicles:
        trips_count = v.trips.filter(status='Completed').count()
        rev = v.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
        fuel_c = v.fuel_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        maint_c = v.maintenance_logs.aggregate(total=Sum('cost'))['total'] or Decimal('0.00')
        exp_c = v.expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        total_cost = fuel_c + maint_c + exp_c
        profit = rev - total_cost
        roi = (profit / v.acquisition_cost * 100) if v.acquisition_cost > 0 else Decimal('0.00')
        
        vehicles_report.append({
            'registration_number': v.registration_number,
            'model': f"{v.make} {v.model}",
            'trips': trips_count,
            'revenue': rev,
            'cost': total_cost,
            'profit': profit,
            'roi': roi
        })
        
    html = f"""
    <html>
    <head>
        <title>Vehicle Performance Report</title>
        <style>
            body {{ font-family: sans-serif; padding: 20px; }}
            h1 {{ text-align: center; color: #1e293b; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; }}
            th {{ background-color: #f1f5f9; }}
        </style>
    </head>
    <body onload="window.print()">
        <h1>Vehicle Performance Report</h1>
        <table>
            <thead>
                <tr>
                    <th>REG</th>
                    <th>MODEL</th>
                    <th>TRIPS</th>
                    <th>REVENUE</th>
                    <th>COST</th>
                    <th>PROFIT</th>
                    <th>ROI</th>
                </tr>
            </thead>
            <tbody>
    """
    for item in vehicles_report:
        html += f"""
                <tr>
                    <td>{item['registration_number']}</td>
                    <td>{item['model']}</td>
                    <td>{item['trips']}</td>
                    <td>₹{item['revenue']:,.2f}</td>
                    <td>₹{item['cost']:,.2f}</td>
                    <td>₹{item['profit']:,.2f}</td>
                    <td>{item['roi']:.2f}%</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return HttpResponse(html)

@login_required
def export_drivers_pdf(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Fleet Manager', 'Financial Analyst']).exists()):
        raise PermissionDenied()
        
    drivers = Driver.objects.all()
    drivers_report = []
    for d in drivers:
        total_trips = d.trips.count()
        comp_trips = d.trips.filter(status='Completed').count()
        fuel = d.trips.filter(status='Completed').aggregate(total=Sum('fuel_consumed'))['total'] or Decimal('0.00')
        rev = d.trips.filter(status='Completed').aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
        
        drivers_report.append({
            'name': d.name,
            'total_trips': total_trips,
            'completed_trips': comp_trips,
            'safety_score': d.safety_score,
            'fuel_consumed': fuel,
            'revenue': rev,
            'status': d.status
        })
        
    html = f"""
    <html>
    <head>
        <title>Driver Performance Report</title>
        <style>
            body {{ font-family: sans-serif; padding: 20px; }}
            h1 {{ text-align: center; color: #1e293b; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; }}
            th {{ background-color: #f1f5f9; }}
        </style>
    </head>
    <body onload="window.print()">
        <h1>Driver Performance Report</h1>
        <table>
            <thead>
                <tr>
                    <th>DRIVER NAME</th>
                    <th>TOTAL TRIPS</th>
                    <th>COMPLETED TRIPS</th>
                    <th>SAFETY SCORE</th>
                    <th>FUEL CONSUMED (L)</th>
                    <th>TOTAL REVENUE</th>
                    <th>STATUS</th>
                </tr>
            </thead>
            <tbody>
    """
    for item in drivers_report:
        html += f"""
                <tr>
                    <td>{item['name']}</td>
                    <td>{item['total_trips']}</td>
                    <td>{item['completed_trips']}</td>
                    <td>{item['safety_score']}</td>
                    <td>{item['fuel_consumed']:.2f} L</td>
                    <td>₹{item['revenue']:,.2f}</td>
                    <td>{item['status']}</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return HttpResponse(html)
