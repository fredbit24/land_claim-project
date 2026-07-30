from django.contrib import admin
from .models import Parcel, OverlapFlag, DisputeReport, AuditBlock


@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ["parcel_id", "owner_name", "zone", "status", "registered_at"]
    list_filter = ["status", "zone"]
    search_fields = ["parcel_id", "owner_name", "zone"]


@admin.register(OverlapFlag)
class OverlapFlagAdmin(admin.ModelAdmin):
    list_display = ["parcel_a", "parcel_b", "overlap_area_sqm", "detected_at"]


@admin.register(DisputeReport)
class DisputeReportAdmin(admin.ModelAdmin):
    list_display = ["parcel", "reporter_name", "resolved", "created_at"]
    list_filter = ["resolved"]

@admin.register(AuditBlock)
class AuditBlockAdmin(admin.ModelAdmin):
    list_display = ["block_index", "event_type", "timestamp", "hash"]
    readonly_fields = ["block_index", "timestamp", "event_type", "payload", "previous_hash", "hash"]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False