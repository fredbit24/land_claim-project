---
title: PostGIS Migration for Geospatial Operations
date: 2026-07-28
status: accepted
---

## Status
Accepted (prototype phase; recommended for production deployment)

## Context
The current implementation stores parcel boundaries as JSON arrays of [lat, lng] points and performs geometric operations using Shapely with a flat-earth coordinate approximation (1 degree ≈ 111,000 meters). This works correctly for small areas near the equator but introduces scaling errors at higher latitudes (Cameroon is at ~4°N, causing ~0.2% error in longitude-based distance calculations). The SQLite database has no spatial indexing, so overlap detection degrades linearly with the number of parcels.

## Decision
Migrate from SQLite + Shapely to PostgreSQL with PostGIS extension for production deployment. This involves:

1. Changing the DATABASES setting to use `django.contrib.gis.db.backends.postgis`
2. Replacing the JSONField boundary column with a `GeometryField(Polygon)` or `PolygonField` type
3. Updating the geo.py module to use PostGIS native functions (`ST_Intersection`, `ST_Area`) instead of Shapely polygons
4. Adding GiST indexes on geometry columns for O(log n) overlap queries

## Consequences

### Advantages
- Native spatial indexing enables scale to tens/hundreds of thousands of parcels with fast overlap detection
- Accurate distance/area calculations using geodesic methods (not flat approximation)
- Built-in topology validation and repair through PostGIS
- Standard GIS tools and integrations available (QGIS, GeoServer, Mapbox, etc.)
- Better support for coordinate reference system transformations (e.g., WGS84 → UTM zone 33N for Cameroon)

### Costs & Risks
- Requires database upgrade from SQLite to PostgreSQL (production downtime or data migration needed)
- Additional dependency: `psycopg2` or `pg8000` + `postgis` extension on server
- Developer training required for GIS concepts (SRID, projection, geometry types)
- Initial data migration needed: convert stored JSON boundaries to PostGIS geometries

## Alternative Considered: Keep SQLite + Improve Current Approach

We could enhance the current approach by:
- Using `pyproj` for proper coordinate transformation before Shapely operations
- Adding simple B-tree indexes on zone/status fields (already implemented via migration 0005)
- Caching computed polygon objects per parcel to avoid repeated Shapely conversions during batch operations

**Why this was rejected**: While suitable for a prototype, these improvements don't solve the fundamental scalability problem. Overlap detection remains O(n) with no spatial index, and area calculations still require a conversion step that's less efficient than database-side spatial operators. For a land registry system expected to grow, the PostGIS path provides better long-term maintainability and performance.

## Implementation Roadmap

1. **Phase 1 (Prototype)**: Current SQLite+Shapely implementation — complete for demo/validation purposes.
2. **Phase 2 (Staging)**: Create migration script to copy data from SQLite to PostGIS, update Django settings, verify query results match within acceptable tolerance.
3. **Phase 3 (Production)**: Deploy with PostgreSQL/PostGIS, add GiST indexes, monitor performance, implement fallback/shutdown procedures.

## Related Items
- Issue #12: Plan PostgreSQL/PostGIS migration (Medium-term improvement from review report)
- Geo accuracy concern: Flat-earth approximation at Cameroon latitude (Gaps section, Technical Implementation Gaps)