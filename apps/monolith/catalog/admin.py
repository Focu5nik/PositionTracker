from django.contrib import admin

from .models import Company, Location, Membership, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "tenant")
    search_fields = ("name", "tenant__name")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "company__name", "fake_external_place_id")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tenant", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "tenant__name")
