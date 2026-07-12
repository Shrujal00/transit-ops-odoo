from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
import datetime
from .models import Vehicle, Driver

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
            capacity_kg=0, # Invalid: must be > 0
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
            acquisition_cost=-50.00 # Invalid: must be > 0
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
