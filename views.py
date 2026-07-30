from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Count
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Parcel, OverlapFlag, DisputeReport, Profile, Notary, Contract, AuditBlock
from .serializers import (
    ParcelSerializer, ParcelPublicSerializer, ParcelDetailSerializer,
    DisputeReportSerializer, ProfileSerializer, RegisterUserSerializer,
    CustomTokenObtainPairSerializer, NotarySerializer, ContractSerializer,
)
from .geo import find_overlaps
from .audit import validate_chain


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def current_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        # Handle text fields
        email = request.data.get("email", request.user.email)
        if isinstance(email, str):
            email = email.strip()
        phone_number = request.data.get("phone_number", profile.phone_number)
        if isinstance(phone_number, str):
            phone_number = phone_number.strip()
        if email and User.objects.exclude(pk=request.user.pk).filter(email__iexact=email).exists():
            return Response({"email": ["This email address is already in use."]}, status=400)
        request.user.email = email
        request.user.save(update_fields=["email"])
        profile.phone_number = phone_number
        profile_fields = ["phone_number"]

        # Handle profile picture upload
        if "profile_picture" in request.FILES:
            profile.profile_picture = request.FILES["profile_picture"]
            profile_fields.append("profile_picture")

        # Handle profile picture removal
        if request.data.get("remove_profile_picture") in ("true", "1", True):
            profile.profile_picture = None
            profile_fields.append("profile_picture")

        profile.save(update_fields=profile_fields)
    return Response(ProfileSerializer(profile).data)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register_user(request):
    serializer = RegisterUserSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response({"detail": "Account created.", "username": user.username}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def search_parcels(request):
    """Public search: by exact parcel_id, or free text match on zone/owner name."""
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response({"detail": "Provide a query parameter 'q'."}, status=400)

    exact = Parcel.objects.filter(parcel_id__iexact=q)
    if exact.exists():
        results = exact
    else:
        results = Parcel.objects.filter(Q(zone__icontains=q) | Q(owner_name__icontains=q))

    serializer = ParcelPublicSerializer(results, many=True)
    return Response({"count": results.count(), "results": serializer.data})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def parcel_listings(request):
    zone = request.query_params.get("zone", "").strip()
    qs = Parcel.objects.filter(for_sale=True).exclude(status__in=["flagged", "disputed"]).order_by("-listed_at", "-registered_at")
    if zone:
        qs = qs.filter(zone__icontains=zone)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = ParcelPublicSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    serializer = ParcelPublicSerializer(qs, many=True)
    return Response({"count": qs.count(), "results": serializer.data})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def parcel_detail(request, pk):
    parcel = Parcel.objects.filter(pk=pk).first()
    if not parcel:
        return Response({"detail": "Parcel not found."}, status=404)
    serializer = ParcelDetailSerializer(parcel)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def register_parcel(request):
    """Notary/registrar endpoint. Runs geometric overlap detection before saving."""
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found. Please contact administrator."}, status=400)
    if profile.role != "notary":
        return Response({"detail": "Only notaries may register new parcels."}, status=403)

    serializer = ParcelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    boundary = serializer.validated_data["boundary"]

    conflicts = find_overlaps(boundary, Parcel.objects.all())

    with transaction.atomic():
        parcel = serializer.save(
            registered_by=request.user,
            seller=request.user,
            owner=request.user,
            status="flagged" if conflicts else "active",
        )
        for other_parcel, area in conflicts:
            OverlapFlag.objects.get_or_create(
                parcel_a=parcel, parcel_b=other_parcel,
                defaults={"overlap_area_sqm": area},
            )
            if other_parcel.status == "active":
                other_parcel.status = "flagged"
                other_parcel.save(update_fields=["status"])

    response_data = ParcelPublicSerializer(parcel).data
    if conflicts:
        return Response(
            {
                "detail": "Registration held: boundary overlaps an existing parcel.",
                "parcel": response_data,
                "conflicts": [
                    {"parcel_id": p.parcel_id, "owner_name": p.owner_name, "overlap_area_sqm": a}
                    for p, a in conflicts
                ],
            },
            status=status.HTTP_201_CREATED,
        )
    return Response({"detail": "Parcel registered.", "parcel": response_data}, status=status.HTTP_201_CREATED)


class DisputeReportCreateView(generics.CreateAPIView):
    queryset = DisputeReport.objects.all()
    serializer_class = DisputeReportSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        dispute = serializer.save()
        parcel = dispute.parcel
        if parcel.status == "active":
            parcel.status = "disputed"
            parcel.save(update_fields=["status"])


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def hotspot_summary(request):
    """Aggregate counts per zone for the regulator hotspot view."""
    zones = (
        Parcel.objects.values("zone")
        .annotate(
            total=Count("id"),
            flagged=Count("id", filter=Q(status="flagged")),
            disputed=Count("id", filter=Q(status="disputed")),
        )
        .order_by("-flagged", "-disputed")
    )
    return Response(list(zones))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notary_directory(request):
    zone = request.query_params.get("zone", "").strip()
    qs = Notary.objects.filter(is_verified=True)
    if zone:
        qs = qs.filter(office_zone__icontains=zone)
    serializer = NotarySerializer(qs, many=True)
    return Response(serializer.data)

@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def my_listings(request):
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found."}, status=400)
    if profile.role != "seller":
        return Response({"detail": "Seller access required."}, status=403)
    qs = Parcel.objects.filter(Q(seller=request.user) | Q(registered_by=request.user) | Q(owner=request.user)).order_by("-listed_at", "-registered_at").distinct()
    if request.method == "GET":
        # Annotate with contract counts
        qs = qs.annotate(
            pending_contracts=Count("contracts", filter=Q(contracts__status="pending")),
            active_contracts=Count("contracts", filter=Q(contracts__status="in_progress")),
            completed_contracts=Count("contracts", filter=Q(contracts__status="completed")),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(ParcelPublicSerializer(page, many=True).data)
        return Response(ParcelPublicSerializer(qs, many=True).data)
    parcel = qs.filter(pk=request.data.get("parcel_id")).first()
    if not parcel:
        return Response({"detail": "Listing not found."}, status=404)

    # If trying to list for sale, validate the parcel can be sold
    if bool(request.data.get("for_sale", parcel.for_sale)):
        # Check if the current user is still the legal owner
        if parcel.owner and parcel.owner != request.user:
            return Response(
                {"detail": "You are no longer the owner of this parcel. Ownership has been transferred."},
                status=403,
            )
        # Check for active contracts (pending or in_progress)
        active_statuses = ["pending", "in_progress"]
        if Contract.objects.filter(parcel=parcel, status__in=active_statuses).exists():
            return Response(
                {"detail": "This parcel has an active contract in progress. It cannot be re-listed until the contract is completed or cancelled."},
                status=400,
            )

    parcel.for_sale = bool(request.data.get("for_sale", parcel.for_sale))
    if "asking_price" in request.data:
        parcel.asking_price = request.data["asking_price"] or None
    if parcel.for_sale and not parcel.listed_at:
        from django.utils import timezone
        parcel.listed_at = timezone.now()
    parcel.save(update_fields=["for_sale", "asking_price", "listed_at"])
    return Response(ParcelPublicSerializer(parcel).data)

@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def contracts_mine(request):
    if request.method == "GET":
        qs = Contract.objects.filter(Q(buyer=request.user) | Q(seller=request.user)).order_by("-created_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(ContractSerializer(page, many=True).data)
        return Response(ContractSerializer(qs, many=True).data)

    serializer = ContractSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found."}, status=400)
    if profile.role != "buyer":
        return Response({"detail": "Only buyers may create contracts."}, status=403)

    # Use select_for_update to prevent race conditions on contract creation
    with transaction.atomic():
        parcel = Parcel.objects.select_for_update().get(pk=serializer.validated_data["parcel_id"])

        if not parcel.for_sale:
            return Response({"detail": "This parcel is not currently for sale."}, status=400)

        # Check for existing active contracts on this parcel
        active_statuses = ["pending", "in_progress"]
        if Contract.objects.filter(parcel=parcel, status__in=active_statuses).exists():
            return Response(
                {"detail": "This parcel already has an active contract. Another contract cannot be created while a sale is in progress."},
                status=400,
            )

        # Immediately mark parcel as not for sale to prevent double-contracting
        parcel.for_sale = False
        parcel.save(update_fields=["for_sale"])

        contract = Contract.objects.create(
            parcel=parcel,
            buyer=request.user,
            seller=parcel.owner or parcel.seller or parcel.registered_by or request.user,
            status="pending",
            notes=serializer.validated_data.get("notes", ""),
        )

    return Response(ContractSerializer(contract).data, status=201)


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_contract(request, pk):
    try:
        contract = Contract.objects.select_related("parcel", "buyer", "seller").get(pk=pk)
    except Contract.DoesNotExist:
        return Response({"detail": "Contract not found."}, status=404)
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found."}, status=400)

    # Buyer can only cancel their own pending contract
    if request.user == contract.buyer and contract.status == "pending" and request.data.get("status") == "cancelled":
        with transaction.atomic():
            contract.status = "cancelled"
            contract.save(update_fields=["status", "updated_at"])
            # Re-allow sale since the contract was cancelled
            contract.parcel.for_sale = True
            contract.parcel.save(update_fields=["for_sale"])
        return Response(ContractSerializer(contract).data)

    # Seller can advance contract: pending -> in_progress -> completed
    if request.user == contract.seller and request.data.get("status") in {"in_progress", "completed"}:
        with transaction.atomic():
            # Lock the parcel for atomicity
            parcel = Parcel.objects.select_for_update().get(pk=contract.parcel_id)

            if request.data["status"] == "in_progress" and contract.status != "pending":
                return Response({"detail": "Only pending contracts can be moved to in_progress."}, status=400)
            if request.data["status"] == "completed" and contract.status != "in_progress":
                return Response({"detail": "Only in_progress contracts can be completed."}, status=400)

            contract.status = request.data["status"]
            contract.save(update_fields=["status", "updated_at"])

            if contract.status == "completed":
                # Transfer ownership to the buyer
                parcel.owner = contract.buyer
                parcel.owner_name = contract.buyer.get_full_name() or contract.buyer.username
                parcel.for_sale = False
                parcel.seller = None
                parcel.save(update_fields=["owner", "owner_name", "for_sale", "seller"])

        return Response(ContractSerializer(contract).data)

    return Response({"detail": "You are not allowed to change this contract."}, status=403)


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def parcel_documents(request, pk):
    """Upload or retrieve documents (title_deed, survey_plan) for a parcel."""
    parcel = Parcel.objects.filter(pk=pk).first()
    if not parcel:
        return Response({"detail": "Parcel not found."}, status=404)
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found."}, status=400)
    # Only the seller/registrar or staff may upload
    if request.user != parcel.seller and request.user != parcel.registered_by and not request.user.is_staff:
        return Response({"detail": "You do not have permission to modify this parcel."}, status=403)
    if request.method == "GET":
        return Response({
            "title_deed": request.build_absolute_uri(parcel.title_deed.url) if parcel.title_deed else None,
            "survey_plan": request.build_absolute_uri(parcel.survey_plan.url) if parcel.survey_plan else None,
        })
    # PATCH - upload files
    if "title_deed" in request.FILES:
        parcel.title_deed = request.FILES["title_deed"]
    if "survey_plan" in request.FILES:
        parcel.survey_plan = request.FILES["survey_plan"]
    parcel.save(update_fields=["title_deed", "survey_plan"] if any(k in request.FILES for k in ("title_deed", "survey_plan")) else [])
    return Response({
        "detail": "Documents updated.",
        "title_deed": request.build_absolute_uri(parcel.title_deed.url) if parcel.title_deed else None,
        "survey_plan": request.build_absolute_uri(parcel.survey_plan.url) if parcel.survey_plan else None,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def admin_dashboard(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({"detail": "Admin access required."}, status=403)
    pending_disputes = DisputeReport.objects.filter(resolved=False).count()
    pending_notaries = Notary.objects.filter(is_verified=False).count()
    zones = (
        Parcel.objects.values("zone")
        .annotate(
            total=Count("id"),
            flagged=Count("id", filter=Q(status="flagged")),
            disputed=Count("id", filter=Q(status="disputed")),
        )
        .order_by("-flagged", "-disputed")
    )
    # List open disputes for moderator review
    open_disputes = DisputeReport.objects.filter(resolved=False).select_related('parcel')
    disputes_list = [
        {
            "id": d.id,
            "parcel_id": d.parcel.parcel_id,
            "owner_name": d.parcel.owner_name,
            "reporter_name": d.reporter_name,
            "description": d.description,
            "created_at": d.created_at.isoformat(),
        }
        for d in open_disputes
    ]
    return Response({
        "pending_disputes": pending_disputes,
        "pending_disputes_list": disputes_list,
        "pending_notaries": pending_notaries,
        "hotspots": list(zones),
    })

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def audit_chain(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({"detail": "Admin access required."}, status=403)
    blocks = AuditBlock.objects.order_by("block_index")
    return Response({
        "validation": validate_chain(),
        "blocks": [{
            "index": block.block_index,
            "timestamp": block.timestamp,
            "event_type": block.event_type,
            "payload": block.payload,
            "previous_hash": block.previous_hash,
            "hash": block.hash,
        } for block in blocks],
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def audit_validate(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({"detail": "Admin access required."}, status=403)
    return Response(validate_chain())


# ====================== Admin User Management ======================

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def admin_users(request):
    """List all users with their profiles. Admin only."""
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({"detail": "Admin access required."}, status=403)
    role_filter = request.query_params.get("role", "").strip()
    qs = Profile.objects.select_related("user").all().order_by("user__date_joined")
    if role_filter:
        qs = qs.filter(role=role_filter)
    serializer = ProfileSerializer(qs, many=True)
    return Response({"count": qs.count(), "users": serializer.data})


@api_view(["PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def admin_user_detail(request, pk):
    """Update or delete a user by profile pk. Admin only."""
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({"detail": "Admin access required."}, status=403)
    try:
        profile = Profile.objects.select_related("user").get(pk=pk)
    except Profile.DoesNotExist:
        return Response({"detail": "User not found."}, status=404)

    if request.method == "DELETE":
        if profile.user == request.user:
            return Response({"detail": "You cannot delete your own account."}, status=400)
        username = profile.user.username
        profile.user.delete()
        return Response({"detail": f"User '{username}' deleted."})

    # PATCH
    role = request.data.get("role", "").strip()
    is_verified = request.data.get("is_verified", None)
    is_staff = request.data.get("is_staff", None)
    is_active = request.data.get("is_active", None)

    if role and role in dict(Profile.ROLE_CHOICES):
        profile.role = role
    if is_verified is not None:
        profile.is_verified = bool(is_verified)
    profile_fields = [k for k in ("role", "is_verified") if k in request.data]
    if profile_fields:
        profile.save(update_fields=profile_fields)

    if is_staff is not None:
        profile.user.is_staff = bool(is_staff)
    if is_active is not None:
        profile.user.is_active = bool(is_active)
    user_fields = [k for k in ("is_staff", "is_active") if k in request.data]
    if user_fields:
        profile.user.save(update_fields=user_fields)

    return Response(ProfileSerializer(profile).data)