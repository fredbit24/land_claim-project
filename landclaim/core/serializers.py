from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Parcel, OverlapFlag, DisputeReport, Profile, Notary, Contract


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    is_staff = serializers.BooleanField(source="user.is_staff", read_only=True)
    is_superuser = serializers.BooleanField(source="user.is_superuser", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Profile
        fields = ["user_id", "username", "email", "role", "phone_number", "is_verified", "is_staff", "is_superuser", "is_active", "date_joined", "profile_picture"]


class RegisterUserSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=[("buyer", "Buyer"), ("seller", "Seller"), ("notary", "Notary")], default="buyer")
    phone_number = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        role = validated_data.pop("role", "buyer")
        phone_number = validated_data.pop("phone_number", "")
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        Profile.objects.create(user=user, role=role, phone_number=phone_number)
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        profile = None
        try:
            profile = self.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.get_or_create(user=self.user)[0]
        data["role"] = getattr(profile, "role", "buyer")
        data["username"] = self.user.username
        data["email"] = self.user.email
        return data


class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = [
            "id", "parcel_id", "owner_name", "owner_phone", "zone", "size_sqm", "boundary",
            "status", "registered_at", "for_sale", "asking_price", "listed_at",
            "title_deed", "survey_plan",
        ]
        read_only_fields = ["id", "parcel_id", "status", "registered_at"]


class ParcelPublicSerializer(serializers.ModelSerializer):
    """What a buyer sees - no owner phone number exposed publicly."""
    overlapping_with = serializers.SerializerMethodField()
    open_disputes = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    pending_contracts = serializers.IntegerField(read_only=True, default=0)
    active_contracts = serializers.IntegerField(read_only=True, default=0)
    completed_contracts = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Parcel
        fields = [
            "id", "parcel_id", "owner_name", "zone", "size_sqm", "boundary", "status",
            "registered_at", "for_sale", "asking_price", "listed_at", "seller_name",
            "overlapping_with", "open_disputes", "title_deed", "survey_plan",
            "pending_contracts", "active_contracts", "completed_contracts",
        ]

    def get_overlapping_with(self, obj):
        flags = OverlapFlag.objects.filter(parcel_a=obj) | OverlapFlag.objects.filter(parcel_b=obj)
        result = []
        for f in flags:
            other = f.parcel_b if f.parcel_a_id == obj.id else f.parcel_a
            result.append({
                "parcel_id": other.parcel_id,
                "owner_name": other.owner_name,
                "overlap_area_sqm": f.overlap_area_sqm,
            })
        return result

    def get_open_disputes(self, obj):
        return obj.disputes.filter(resolved=False).count()

    def get_seller_name(self, obj):
        if obj.seller:
            return obj.seller.get_full_name() or obj.seller.username
        return None


class ParcelDetailSerializer(serializers.ModelSerializer):
    overlapping_with = serializers.SerializerMethodField()
    open_disputes = serializers.SerializerMethodField()
    seller_contact = serializers.SerializerMethodField()
    notary_contact = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = [
            "id", "parcel_id", "owner_name", "owner_phone", "zone", "size_sqm", "boundary",
            "status", "registered_at", "for_sale", "asking_price", "listed_at", "seller_contact",
            "notary_contact", "overlapping_with", "open_disputes", "title_deed", "survey_plan",
        ]

    def get_overlapping_with(self, obj):
        flags = OverlapFlag.objects.filter(parcel_a=obj) | OverlapFlag.objects.filter(parcel_b=obj)
        result = []
        for f in flags:
            other = f.parcel_b if f.parcel_a_id == obj.id else f.parcel_a
            result.append({"parcel_id": other.parcel_id, "owner_name": other.owner_name, "overlap_area_sqm": f.overlap_area_sqm})
        return result

    def get_open_disputes(self, obj):
        return obj.disputes.filter(resolved=False).count()

    def get_seller_contact(self, obj):
        if not obj.seller:
            return None
        try:
            profile = obj.seller.profile
        except Profile.DoesNotExist:
            return None
        return {"name": obj.seller.get_full_name() or obj.seller.username, "phone_number": profile.phone_number, "email": obj.seller.email}

    def get_notary_contact(self, obj):
        notary = Notary.objects.filter(is_verified=True).order_by("id").first()
        if notary:
            return {"full_name": notary.full_name, "phone_number": notary.phone_number, "email": notary.email, "office_zone": notary.office_zone}
        return None


class DisputeReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisputeReport
        fields = ["id", "parcel", "reporter_name", "reporter_contact", "description", "supporting_document", "created_at", "resolved"]
        read_only_fields = ["id", "created_at", "resolved"]


class NotarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Notary
        fields = ["id", "full_name", "phone_number", "email", "office_zone", "is_verified"]

class ContractSerializer(serializers.ModelSerializer):
    parcel_id = serializers.IntegerField(write_only=True)
    parcel_summary = serializers.SerializerMethodField(read_only=True)
    buyer_name = serializers.SerializerMethodField(read_only=True)
    seller_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Contract
        fields = ["id", "parcel", "parcel_id", "buyer", "seller", "status", "notes", "created_at", "updated_at", "parcel_summary", "buyer_name", "seller_name"]
        read_only_fields = ["id", "parcel", "buyer", "seller", "created_at", "updated_at", "parcel_summary", "buyer_name", "seller_name"]

    def get_parcel_summary(self, obj):
        return {"parcel_id": obj.parcel.parcel_id, "owner_name": obj.parcel.owner_name, "zone": obj.parcel.zone}

    def get_buyer_name(self, obj):
        return obj.buyer.get_full_name() or obj.buyer.username

    def get_seller_name(self, obj):
        return obj.seller.get_full_name() or obj.seller.username

    def create(self, validated_data):
        parcel_id = validated_data.pop("parcel_id")
        parcel = Parcel.objects.get(pk=parcel_id)
        validated_data["parcel"] = parcel
        return super().create(validated_data)
