from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError
from django.utils import timezone

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

class Vehicle(models.Model):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('On Trip', 'On Trip'),
        ('In Shop', 'In Shop'),
        ('Retired', 'Retired'),
    ]
    TYPE_CHOICES = [
        ('Truck', 'Truck'),
        ('Van', 'Van'),
        ('Sedan', 'Sedan'),
        ('Other', 'Other'),
    ]
    registration_number = models.CharField(max_length=20, unique=True, db_index=True)
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Truck')
    year = models.PositiveIntegerField()
    capacity_kg = models.PositiveIntegerField()
    odometer = models.PositiveIntegerField(default=0)
    acquisition_cost = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')

    def clean(self):
        super().clean()
        if self.capacity_kg is not None and self.capacity_kg <= 0:
            raise ValidationError({'capacity_kg': 'Capacity must be greater than 0.'})
        if self.acquisition_cost is not None and self.acquisition_cost <= 0:
            raise ValidationError({'acquisition_cost': 'Acquisition cost must be greater than 0.'})

    def save(self, *args, **kwargs):
        if self.registration_number:
            self.registration_number = self.registration_number.upper().strip()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.registration_number} ({self.make} {self.model})"

class Driver(models.Model):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('On Trip', 'On Trip'),
        ('Off Duty', 'Off Duty'),
        ('Suspended', 'Suspended'),
    ]
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='driver_profile')
    name = models.CharField(max_length=100)
    license_number = models.CharField(max_length=50, unique=True)
    license_category = models.CharField(max_length=50, default='Class A')
    license_expiry = models.DateField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    safety_score = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')

    @property
    def is_license_valid(self):
        return self.license_expiry >= timezone.now().date()

    def clean(self):
        super().clean()
        # Add any necessary license format validations or sanity checks here
        
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Trip(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Ongoing', 'Ongoing'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    source = models.CharField(max_length=250)
    destination = models.CharField(max_length=250)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='trips')
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='trips')
    cargo_weight = models.PositiveIntegerField()
    planned_distance = models.PositiveIntegerField(default=0)
    scheduled_date = models.DateField()
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    end_time = models.DateTimeField(null=True, blank=True)
    end_odometer = models.PositiveIntegerField(null=True, blank=True)
    fuel_consumed = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    def clean(self):
        super().clean()
        if self.cargo_weight is not None and self.cargo_weight <= 0:
            raise ValidationError({'cargo_weight': 'Cargo weight must be greater than 0.'})
        if self.revenue is not None and self.revenue < 0:
            raise ValidationError({'revenue': 'Revenue cannot be negative.'})
        if self.planned_distance is not None and self.planned_distance < 0:
            raise ValidationError({'planned_distance': 'Planned distance cannot be negative.'})
            
        if self.vehicle and self.cargo_weight and self.cargo_weight > self.vehicle.capacity_kg:
            raise ValidationError({'cargo_weight': f"Cargo weight ({self.cargo_weight} kg) exceeds vehicle capacity ({self.vehicle.capacity_kg} kg)."})

        if self.status == 'Completed':
            if self.end_odometer is None:
                raise ValidationError({'end_odometer': 'End odometer is required to complete a trip.'})
            if self.fuel_consumed is None or self.fuel_consumed <= 0:
                raise ValidationError({'fuel_consumed': 'Valid fuel consumed (liters) is required to complete a trip.'})
            if self.vehicle and self.end_odometer < self.vehicle.odometer:
                raise ValidationError({'end_odometer': f"End odometer ({self.end_odometer}) cannot be less than vehicle's current odometer ({self.vehicle.odometer})."})
            
        is_new = self.pk is None
        original_status = None
        if not is_new:
            try:
                original = Trip.objects.get(pk=self.pk)
                original_status = original.status
            except Trip.DoesNotExist:
                pass

        if self.status == 'Ongoing' and (is_new or original_status in ['Draft', 'Cancelled']):
            if self.driver:
                if not self.driver.is_license_valid:
                    raise ValidationError({'driver': f"Driver {self.driver.name} has an expired license."})
                if self.driver.status != 'Available':
                    raise ValidationError({'driver': f"Driver {self.driver.name} is not available (current status: {self.driver.status})."})
            if self.vehicle:
                if self.vehicle.status != 'Available':
                    raise ValidationError({'vehicle': f"Vehicle {self.vehicle.registration_number} is not available (current status: {self.vehicle.status})."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Trip {self.id}: {self.source} -> {self.destination}"

class MaintenanceLog(models.Model):
    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='maintenance_logs')
    description = models.TextField()
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')

    def clean(self):
        super().clean()
        if self.cost is not None and self.cost < 0:
            raise ValidationError({'cost': 'Cost cannot be negative.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        original_status = None
        if not is_new:
            try:
                original_status = MaintenanceLog.objects.get(pk=self.pk).status
            except MaintenanceLog.DoesNotExist:
                pass
                
        self.full_clean()
        super().save(*args, **kwargs)
        
        # Enforce state transitions on vehicle
        if self.status in ['In Progress', 'Scheduled']:
            if self.vehicle.status != 'In Shop':
                old_v_status = self.vehicle.status
                self.vehicle.status = 'In Shop'
                self.vehicle.save(update_fields=['status'])
                
                from django.contrib.contenttypes.models import ContentType
                ct = ContentType.objects.get_for_model(self.vehicle)
                AuditLog.objects.create(
                    content_type=ct,
                    object_id=self.vehicle.id,
                    action='Status Change',
                    old_status=old_v_status,
                    new_status='In Shop',
                    details=f"Vehicle status set to In Shop due to maintenance log."
                )
        elif self.status == 'Completed' and (is_new or original_status != 'Completed'):
            # Revert to Available (unless assigned to ongoing trip)
            has_ongoing_trip = self.vehicle.trips.filter(status='Ongoing').exists()
            new_v_status = 'On Trip' if has_ongoing_trip else 'Available'
            
            if self.vehicle.status != new_v_status:
                old_v_status = self.vehicle.status
                self.vehicle.status = new_v_status
                self.vehicle.save(update_fields=['status'])
                
                from django.contrib.contenttypes.models import ContentType
                ct = ContentType.objects.get_for_model(self.vehicle)
                AuditLog.objects.create(
                    content_type=ct,
                    object_id=self.vehicle.id,
                    action='Status Change',
                    old_status=old_v_status,
                    new_status=new_v_status,
                    details=f"Maintenance completed. Vehicle returned to {new_v_status}."
                )

    def __str__(self):
        return f"Maintenance on {self.vehicle.registration_number} ({self.status})"

class FuelLog(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='fuel_logs')
    liters = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    def clean(self):
        super().clean()
        if self.liters is not None and self.liters <= 0:
            raise ValidationError({'liters': 'Liters must be greater than 0.'})
        if self.cost is not None and self.cost <= 0:
            raise ValidationError({'cost': 'Cost must be greater than 0.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Fuel for {self.vehicle.registration_number} on {self.date}"

class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('Insurance', 'Insurance'),
        ('Tolls', 'Tolls'),
        ('Permits', 'Permits'),
        ('Other', 'Other'),
    ]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    date = models.DateField()

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Amount must be greater than 0.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category} expense for {self.vehicle.registration_number} on {self.date}"

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    action = models.CharField(max_length=255)
    old_status = models.CharField(max_length=50, blank=True, null=True)
    new_status = models.CharField(max_length=50, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.action} on {self.content_object}"
