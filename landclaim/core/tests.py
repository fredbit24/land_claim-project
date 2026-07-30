from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Parcel, Profile
from .geo import points_to_polygon, find_overlaps, MIN_OVERLAP_SQM, DEG_TO_M


class GeoTests(TestCase):
    """Unit tests for geometric overlap detection."""

    def test_points_to_polygon_valid(self):
        """Test that valid points form a correct polygon."""
        points = [[0, 0], [0, 1], [1, 1], [1, 0]]
        poly = points_to_polygon(points)
        self.assertIsNotNone(poly)
        self.assertTrue(poly.is_valid)
        # Area should be approximately (1 degree * 111000m)^2 = about 12 billion sq m
        self.assertGreater(poly.area, 0)

    def test_points_to_polygon_invalid_low_points(self):
        """Polygon with fewer than 3 points returns None."""
        points = [[0, 0], [1, 1]]
        result = points_to_polygon(points)
        self.assertIsNone(result)

    def test_points_to_polygon_single_point(self):
        """Single point returns None."""
        points = [[0, 0]]
        result = points_to_polygon(points)
        self.assertIsNone(result)

    def test_find_overlaps_no_conflicts(self):
        """Two non-overlapping parcels return no conflicts."""
        # Non-overlapping squares - far apart
        boundary1 = [[0, 0], [0, 1], [1, 1], [1, 0]]
        boundary2 = [[10, 10], [10, 11], [11, 11], [11, 10]]
        # Create a fake parcel object for testing
        class FakeParcel:
            def __init__(self, boundary):
                self.boundary = boundary
        existing_parcels = [FakeParcel(boundary2)]
        conflicts = find_overlaps(boundary1, existing_parcels)
        self.assertEqual(len(conflicts), 0)

    def test_find_overlaps_with_conflict(self):
        """Overlapping parcels should return conflict with area."""
        # Small overlapping region ~0.001 x 0.001 degrees = about 111m x 111m ≈ 12321 sq m, well above 5 sq m threshold
        boundary1 = [[0, 0], [0, 2], [2, 2], [2, 0]]
        boundary2 = [[1, 1], [1, 3], [3, 3], [3, 1]]
        class FakeParcel:
            def __init__(self, boundary):
                self.boundary = boundary
        existing_parcels = [FakeParcel(boundary2)]
        conflicts = find_overlaps(boundary1, existing_parcels)
        self.assertEqual(len(conflicts), 1)
        parcel, area = conflicts[0]
        self.assertGreater(area, 0)
        self.assertGreaterEqual(area, MIN_OVERLAP_SQM)

    def test_find_overlaps_below_threshold(self):
        """Tiny overlaps below the noise threshold are ignored."""
        # Very tiny overlap less than 5 sq m
        boundary1 = [[0, 0], [0, 0.00001], [0.00001, 0.00001], [0.00001, 0]]
        boundary2 = [[0.000005, 0.000005], [0.000005, 0.000015], [0.000015, 0.000015], [0.000015, 0.000005]]
        class FakeParcel:
            def __init__(self, boundary):
                self.boundary = boundary
        existing_parcels = [FakeParcel(boundary2)]
        conflicts = find_overlaps(boundary1, existing_parcels)
        self.assertEqual(len(conflicts), 0)


class AuthAndListingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create a user for authenticated tests
        self.user = User.objects.create_user(username="testuser", password="testpass123", email="test@example.com")
        Profile.objects.create(user=self.user, role="buyer")

    def _login(self):
        """Obtain JWT token for the test user."""
        response = self.client.post(
            "/api/token/",
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_user_can_register_as_buyer_and_get_profile(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "buyer1",
                "email": "buyer@example.com",
                "password": "StrongPass123",
                "password_confirm": "StrongPass123",
                "role": "buyer",
                "phone_number": "+237650000001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username="buyer1").exists())
        self.assertEqual(Profile.objects.get(user__username="buyer1").role, "buyer")

    def test_listings_endpoint_excludes_flagged_and_disputed_parcels(self):
        self._login()
        Parcel.objects.create(
            owner_name="A",
            zone="Bastos",
            size_sqm=100,
            boundary=[[0, 0], [0, 1], [1, 1], [1, 0]],
            status="active",
            for_sale=True,
            asking_price=1200000,
        )
        Parcel.objects.create(
            owner_name="B",
            zone="Bastos",
            size_sqm=120,
            boundary=[[2, 2], [2, 3], [3, 3], [3, 2]],
            status="flagged",
            for_sale=True,
            asking_price=1500000,
        )
        Parcel.objects.create(
            owner_name="C",
            zone="Bastos",
            size_sqm=140,
            boundary=[[4, 4], [4, 5], [5, 5], [5, 4]],
            status="disputed",
            for_sale=True,
            asking_price=1800000,
        )

        response = self.client.get("/api/parcels/listings/?zone=Bastos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["owner_name"], "A")