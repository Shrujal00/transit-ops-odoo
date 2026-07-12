from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Role, User, Vehicle, Driver, Trip, MaintenanceLog, FuelLog, Expense, AuditLog

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['email', 'role', 'is_staff', 'is_superuser']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),
    )
    ordering = ['email']

admin.site.register(Role)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Vehicle)
admin.site.register(Driver)
admin.site.register(Trip)
admin.site.register(MaintenanceLog)
admin.site.register(FuelLog)
admin.site.register(Expense)
admin.site.register(AuditLog)
