"""
Creates a fictional seller account plus a sample registered parcel,
useful for demos and testing without needing the real notary flow.

Usage:
    python3 manage.py seed_demo_seller
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import Parcel


class Command(BaseCommand):
    help = "Seed a fictional seller user and a sample parcel for demo purposes."

    def handle(self, *args, **options):
        username = "seller_demo"
        password = "seller12345"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": "Ngo", "last_name": "Achu", "email": "ngo.achu@example.com"},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{username}' / password '{password}'"))
        else:
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists, reusing it."))

        parcel, created = Parcel.objects.get_or_create(
            owner_name="Ngo Achu",
            zone="Odza, Yaounde",
            defaults={
                "owner_phone": "677123456",
                "size_sqm": 500,
                "boundary": [[3.8560, 11.5210], [3.8564, 11.5216], [3.8557, 11.5219], [3.8553, 11.5213]],
                "status": "active",
                "registered_by": user,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Created sample parcel {parcel.parcel_id} for Ngo Achu in Odza, Yaounde."
            ))
        else:
            self.stdout.write(self.style.WARNING(f"Parcel for Ngo Achu already exists: {parcel.parcel_id}"))
