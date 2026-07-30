from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Parcel, Profile, Notary


class Command(BaseCommand):
    help = "Seed realistic demo listings for buyers and sellers."

    def handle(self, *args, **options):
        names = [
            ("Mouhammad Talla", "+237650000001"),
            ("Agnès Nkomo", "+237650000002"),
            ("Daniel Fokou", "+237650000003"),
            ("Grace Mvondo", "+237650000004"),
            ("Eric Biyong", "+237650000005"),
            ("Lydia Enoh", "+237650000006"),
            ("Boris Nguefack", "+237650000007"),
            ("Marthe Ntankou", "+237650000008"),
            ("Paul Tchoua", "+237650000009"),
            ("Nadine Mballa", "+237650000010"),
        ]
        for idx, (name, phone) in enumerate(names, start=1):
            username = f"seller{idx}"
            user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com", "first_name": name.split()[0], "last_name": " ".join(name.split()[1:])})
            if created:
                user.set_password("seller12345")
                user.save()
            Profile.objects.get_or_create(user=user, defaults={"role": "seller", "phone_number": phone})
            parcel, parcel_created = Parcel.objects.get_or_create(
                owner_name=name,
                zone=["Bastos", "Mokolo", "Mendong", "Nkolbisson", "Bonamoussadi", "Bonanjo", "Etoa", "Mvolye", "Awae", "Nsam"][idx - 1],
                defaults={
                    "owner_phone": phone,
                    "size_sqm": 450 + idx * 30,
                    "boundary": [[3.85 + idx * 0.001, 11.50 + idx * 0.001], [3.85 + idx * 0.001, 11.51 + idx * 0.001], [3.86 + idx * 0.001, 11.51 + idx * 0.001], [3.86 + idx * 0.001, 11.50 + idx * 0.001]],
                    "status": "active",
                    "seller": user,
                    "for_sale": True,
                    "asking_price": Decimal(12000000 + idx * 500000),
                    "listed_at": timezone.now(),
                    "registered_by": user,
                },
            )
            if parcel_created:
                self.stdout.write(self.style.SUCCESS(f"Created listing for {name}"))
            else:
                parcel.seller = user
                parcel.for_sale = True
                parcel.asking_price = Decimal(12000000 + idx * 500000)
                parcel.listed_at = timezone.now()
                parcel.save(update_fields=["seller", "for_sale", "asking_price", "listed_at"])
        Notary.objects.get_or_create(
            full_name="Dr. Patrice Belinga",
            defaults={"phone_number": "+237699000111", "email": "patrice.belinga@example.com", "office_zone": "Bastos", "is_verified": True},
        )
        self.stdout.write(self.style.SUCCESS("Seed data ready."))