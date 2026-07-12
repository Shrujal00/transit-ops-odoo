from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import Group
import datetime
from .models import Role, User, Vehicle, Driver

class VehicleModelTest(TestCase):
    def test_registration_number_uppercase_on_save(self):
        vehicle = Vehicle.objects.create(
            registration_number="  tx-4589-k  ",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=1200,
            acquisition_cost=35000.00
        )
        self.assertEqual(vehicle.registration_number, "TX-4589-K")

    def test_invalid_capacity_raises_validation_error(self):
        vehicle = Vehicle(
            registration_number="TX-1111-B",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=0,
            acquisition_cost=35000.00
        )
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_invalid_acquisition_cost_raises_validation_error(self):
        vehicle = Vehicle(
            registration_number="TX-1111-B",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=1200,
            acquisition_cost=-50.00
        )
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

class DriverModelTest(TestCase):
    def test_is_license_valid_with_future_expiry(self):
        expiry = timezone.now().date() + datetime.timedelta(days=10)
        driver = Driver(
            name="John Doe",
            license_number="DL-12345",
            license_expiry=expiry,
            status="Available"
        )
        self.assertTrue(driver.is_license_valid)

    def test_is_license_valid_with_past_expiry(self):
        expiry = timezone.now().date() - datetime.timedelta(days=1)
        driver = Driver(
            name="Jane Doe",
            license_number="DL-54321",
            license_expiry=expiry,
            status="Available"
        )
        self.assertFalse(driver.is_license_valid)

class ViewGuardsRBACTest(TestCase):
    def setUp(self):
        # Create roles
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.driver_role = Role.objects.create(name="Driver", code="driver")
        
        # Create Groups
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.driver_group = Group.objects.create(name="Driver")
        
        # Create Users
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        self.driver_user_1 = User.objects.create_user(email="driver1@test.com", password="password123", role=self.driver_role)
        self.driver_user_1.groups.add(self.driver_group)

        self.driver_user_2 = User.objects.create_user(email="driver2@test.com", password="password123", role=self.driver_role)
        self.driver_user_2.groups.add(self.driver_group)

        # Create Vehicles & Drivers
        self.vehicle = Vehicle.objects.create(
            registration_number="TX-9988-V", make="Ford", model="Transit", year=2020, capacity_kg=3000, acquisition_cost=40000.00
        )
        self.driver_1 = Driver.objects.create(
            user=self.driver_user_1, name="John Driver 1", license_number="LIC-111", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )
        self.driver_2 = Driver.objects.create(
            user=self.driver_user_2, name="Jane Driver 2", license_number="LIC-222", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )

    def test_unauthenticated_user_redirects_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_fleet_manager_can_access_vehicle_crud(self):
        self.client.login(email="manager@test.com", password="password123")
        
        # List
        response = self.client.get(reverse('vehicle_list'))
        self.assertEqual(response.status_code, 200)

        # Create view
        response = self.client.get(reverse('vehicle_create'))
        self.assertEqual(response.status_code, 200)

    def test_driver_blocked_from_vehicle_create(self):
        self.client.login(email="driver1@test.com", password="password123")
        
        # Blocked from creating vehicle (returns 403 Forbidden)
        response = self.client.get(reverse('vehicle_create'))
        self.assertEqual(response.status_code, 403)

    def test_driver_blocked_from_driver_list(self):
        self.client.login(email="driver1@test.com", password="password123")
        
        # Driver cannot view the registry list of all drivers
        response = self.client.get(reverse('driver_list'))
        self.assertEqual(response.status_code, 403)

    def test_driver_can_view_own_detail_but_blocked_from_other_driver_detail(self):
        self.client.login(email="driver1@test.com", password="password123")
        
        # Can view own detail profile
        response = self.client.get(reverse('driver_detail', kwargs={'pk': self.driver_1.pk}))
        self.assertEqual(response.status_code, 200)
        
        # Blocked from viewing other driver detail profile
        response = self.client.get(reverse('driver_detail', kwargs={'pk': self.driver_2.pk}))
        self.assertEqual(response.status_code, 403)
