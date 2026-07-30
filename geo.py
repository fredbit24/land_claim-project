"""
Overlap detection: converts stored [lat, lng] boundary points into shapely
polygons and checks whether a new parcel's boundary meaningfully overlaps
any existing parcel's boundary. This is the core anti-fraud mechanism -
it is what catches the same plot of land being registered to two owners.
"""
from shapely.geometry import Polygon

# Minimum overlapping area (in square meters, approximated) before we treat
# it as a real conflict rather than a rounding/GPS-noise artifact.
MIN_OVERLAP_SQM = 5.0

# Rough conversion: at the equator-ish latitudes relevant to Cameroon,
# 1 degree of latitude/longitude is approximately 111,000 meters.
DEG_TO_M = 111000.0


def points_to_polygon(points):
    """points: list of [lat, lng] -> shapely Polygon in meters (local flat approx)."""
    if len(points) < 3:
        return None
    coords = [(lng * DEG_TO_M, lat * DEG_TO_M) for lat, lng in points]
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def find_overlaps(new_boundary, existing_parcels):
    """
    new_boundary: list of [lat, lng] points for the parcel being registered.
    existing_parcels: queryset of Parcel objects to check against.
    Returns list of (parcel, overlap_area_sqm) for every real conflict found.
    """
    new_poly = points_to_polygon(new_boundary)
    if new_poly is None or not new_poly.is_valid or new_poly.area == 0:
        return []

    conflicts = []
    for parcel in existing_parcels:
        existing_poly = points_to_polygon(parcel.boundary)
        if existing_poly is None or not existing_poly.is_valid:
            continue
        if new_poly.intersects(existing_poly):
            intersection_area = new_poly.intersection(existing_poly).area
            if intersection_area >= MIN_OVERLAP_SQM:
                conflicts.append((parcel, round(intersection_area, 2)))
    return conflicts
