import uuid
from django.db import models
from django.contrib.auth.models import User


def generate_parcel_id():
    from django.utils import timezone
    year = timezone.now().year
    suffix = uuid.uuid4().hex[:5].upper()
    return f"PLT-{year}-{suffix}"


class Profile(models.Model):
    ROLE_CHOICES = [
        ("buyer", "Buyer"),
        ("seller", "Seller"),
        ("notary", "Notary"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="buyer")
    phone_number = models.CharField(max_length=30, blank=True)
    is_verified = models.BooleanField(default=False, help_text="Admin-verified seller/notary")
    profile_picture = models.ImageField(upload_to="profiles/pictures/", null=True, blank=True, help_text="Upload a profile picture")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role}){' ✓' if self.is_verified else ''}"


class Notary(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notary_profile")
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    office_zone = models.CharField(max_length=200, blank=True)
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name or self.office_zone or "Notary"


class Parcel(models.Model):
    STATUS_CHOICES = [
        ("active", "Active - no conflicts"),
        ("flagged", "Flagged - overlapping claim"),
        ("disputed", "Disputed - report filed"),
    ]

    parcel_id = models.CharField(max_length=20, unique=True, default=generate_parcel_id, editable=False)
    owner_name = models.CharField(max_length=200)
    owner_phone = models.CharField(max_length=30, blank=True)
    zone = models.CharField(max_length=200, help_text="e.g. Bastos, Yaounde")
    size_sqm = models.FloatField(help_text="Approximate size in square meters")
    boundary = models.JSONField(help_text="List of [lat, lng] points forming the parcel boundary")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="registered_parcels")
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_parcels")
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_parcels", help_text="Current legal owner of the parcel")
    for_sale = models.BooleanField(default=False)
    asking_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    listed_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    # Document uploads
    title_deed = models.FileField(upload_to="documents/title_deeds/", null=True, blank=True, help_text="Upload the title deed document")
    survey_plan = models.FileField(upload_to="documents/survey_plans/", null=True, blank=True, help_text="Upload the survey plan")

    class Meta:
        indexes = [
            models.Index(fields=['zone'], name='parcel_zone_idx'),
            models.Index(fields=['status'], name='parcel_status_idx'),
            models.Index(fields=['for_sale'], name='parcel_for_sale_idx'),
            models.Index(fields=['-registered_at'], name='parcel_registered_at_idx'),
            models.Index(fields=['-listed_at'], name='parcel_listed_at_idx'),
            models.Index(fields=['-listed_at', '-registered_at'], name='parcel_recent_listings_idx'),
            models.Index(fields=['zone', 'status'], name='parcel_zone_status_idx'),
        ]

    def __str__(self):
        return f"{self.parcel_id} ({self.owner_name})"


class OverlapFlag(models.Model):
    parcel_a = models.ForeignKey(Parcel, on_delete=models.CASCADE, related_name="overlaps_as_a")
    parcel_b = models.ForeignKey(Parcel, on_delete=models.CASCADE, related_name="overlaps_as_b")
    overlap_area_sqm = models.FloatField()
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("parcel_a", "parcel_b")

    def __str__(self):
        return f"Overlap: {self.parcel_a.parcel_id} <-> {self.parcel_b.parcel_id}"


class DisputeReport(models.Model):
    parcel = models.ForeignKey(Parcel, on_delete=models.CASCADE, related_name="disputes")
    reporter_name = models.CharField(max_length=200)
    reporter_contact = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    supporting_document = models.FileField(upload_to="documents/disputes/", null=True, blank=True, help_text="Upload supporting evidence")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['parcel'], name='dispute_parcel_idx'),
            models.Index(fields=['resolved'], name='dispute_resolved_idx'),
        ]

    def __str__(self):
        return f"Dispute on {self.parcel.parcel_id} by {self.reporter_name}"


class Contract(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    parcel = models.ForeignKey(Parcel, on_delete=models.CASCADE, related_name="contracts")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts_as_buyer")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts_as_seller")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='contract_status_idx'),
            models.Index(fields=['-created_at'], name='contract_created_at_idx'),
            models.Index(fields=['buyer'], name='contract_buyer_idx'),
            models.Index(fields=['seller'], name='contract_seller_idx'),
        ]

    def __str__(self):
        return f"{self.parcel.parcel_id} :: {self.buyer.username} -> {self.seller.username}"

class AuditBlock(models.Model):
    """Tamper-evident, append-only audit ledger for marketplace events."""
    block_index = models.PositiveIntegerField(unique=True)
    timestamp = models.DateTimeField()
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    previous_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["block_index"]

    def __str__(self):
        return f"Block {self.block_index}: {self.event_type}"