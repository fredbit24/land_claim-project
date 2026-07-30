from django.db.models.signals import post_save
from django.dispatch import receiver
from .audit import append_audit_event
from .models import Parcel, Contract, DisputeReport

@receiver(post_save, sender=Parcel)
def audit_parcel(sender, instance, created, **kwargs):
    append_audit_event("parcel.created" if created else "parcel.updated", {
        "parcel_id": instance.parcel_id, "zone": instance.zone, "status": instance.status,
        "for_sale": instance.for_sale, "asking_price": str(instance.asking_price or ""),
    })

@receiver(post_save, sender=Contract)
def audit_contract(sender, instance, created, **kwargs):
    append_audit_event("contract.created" if created else "contract.updated", {
        "contract_id": instance.id, "parcel_id": instance.parcel.parcel_id, "status": instance.status,
        "buyer": instance.buyer.username, "seller": instance.seller.username,
    })

@receiver(post_save, sender=DisputeReport)
def audit_dispute(sender, instance, created, **kwargs):
    if created:
        append_audit_event("dispute.created", {"dispute_id": instance.id, "parcel_id": instance.parcel.parcel_id})