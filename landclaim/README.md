# Landclaim

A working prototype of the land parcel fraud-detection engine described in
the project brief. This is a real Django + DRF backend with genuine
geometric overlap detection (using Shapely), plus a single-page frontend
that exercises the full API. It is not a mockup — every button in the
frontend hits a real endpoint and real database.

## What's implemented

- **Public parcel search** (`GET /api/parcels/search/?q=...`) — search by
  exact parcel ID or by zone/owner name. No login required, mirrors what a
  buyer would use.
- **Notary/registrar parcel registration** (`POST /api/parcels/register/`,
  requires JWT login) — registers a new parcel and runs it against every
  existing parcel's boundary using polygon intersection. If the overlap
  area exceeds a small noise threshold (5 m²), both parcels are
  automatically flagged and an `OverlapFlag` record is created linking
  them. This is the core anti-double-sale mechanism.
- **Dispute reporting** (`POST /api/disputes/`) — public endpoint, sets
  the parcel status to "disputed" on first report.
- **Hotspot summary** (`GET /api/hotspots/`) — aggregate flagged/disputed
  counts per zone, for a future regulator dashboard.
- **Django admin** at `/admin/` for browsing/moderating records directly.

## What's intentionally left as a next step

- The frontend boundary input is a raw JSON array of `[lat, lng]` points
  for clarity. A production version would let a notary draw the boundary
  on a map (e.g. Leaflet/Mapbox draw tools) and would submit real GPS
  coordinates.
- No file upload for title deeds/ID documents yet — the DisputeReport and
  Parcel models can be extended with a `FileField` for this.
- No SMS/push notification on flagging — the OverlapFlag model captures
  the data needed to trigger this later.
- Authentication is JWT via Simple JWT; there's no manufacturer/notary
  self-signup flow yet — accounts are created via `createsuperuser` or
  the admin panel, matching the brief's "administrator approves
  manufacturers" pattern.

## Project structure

```
landclaim/
  landclaim/        Django project settings, root urls
  core/
    models.py        Parcel, OverlapFlag, DisputeReport
    geo.py            Overlap detection logic (Shapely)
    serializers.py
    views.py          Search, register, dispute, hotspot endpoints
    urls.py
    admin.py
  frontend/
    index.html        Single-page app: buyer search, notary registration, dispute form
  manage.py
  requirements.txt
```

## Running it locally

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 manage.py migrate
python3 manage.py createsuperuser   # create your own notary/admin login
python3 manage.py runserver
```

Then open `http://127.0.0.1:8000/` in a browser.

No pre-seeded accounts exist. Create an administrative user via:<br>
```bash<br>python3 manage.py createsuperuser<br>```\n\nTo create a notary account during development, you can also create a User and Profile through the Django shell or admin interface.

## Trying the overlap detection yourself

1. Go to the **Notary registration** tab, log in with `notary1` /
   `landclaim123`.
2. Register a parcel with this boundary:
   `[[3.8721,11.5021],[3.8725,11.5028],[3.8719,11.5030],[3.8716,11.5023]]`
3. Register a second parcel under a different owner name with an
   overlapping boundary, e.g.:
   `[[3.8722,11.5022],[3.8726,11.5029],[3.8718,11.5031],[3.8715,11.5024]]`
4. You'll see the conflict detected immediately, with the overlap area
   in square meters. Go to **Buyer search** and search either parcel ID —
   both will now show as flagged with a link to the conflicting claim.

## API summary

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/api/parcels/search/?q=` | none | Buyer search by ID/zone/owner |
| POST | `/api/parcels/register/` | JWT | Register a parcel, runs overlap check |
| POST | `/api/disputes/` | none | File a dispute report |
| GET | `/api/hotspots/` | none | Per-zone flagged/disputed counts |
| POST | `/api/token/` | none | Get JWT access/refresh token |

## Extending toward the full brief

The Parcel/OverlapFlag/DisputeReport models and the `find_overlaps()`
function in `core/geo.py` are the reusable core. Everything else in the
original brief (hotspot map UI, notifications, manufacturer approval
workflow) is standard CRUD/dashboard work layered on top of this engine —
happy to build any of those next.

