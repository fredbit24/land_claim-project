from django.urls import path
from . import views

urlpatterns = [
    path("auth/register/", views.register_user, name="register-user"),
    path("auth/me/", views.current_profile, name="current-profile"),
    path("seller/listings/", views.my_listings, name="my-listings"),
    path("token/", views.CustomTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("parcels/search/", views.search_parcels, name="search-parcels"),
    path("parcels/listings/", views.parcel_listings, name="parcel-listings"),
    path("parcels/<int:pk>/", views.parcel_detail, name="parcel-detail"),
    path("parcels/register/", views.register_parcel, name="register-parcel"),
    path("disputes/", views.DisputeReportCreateView.as_view(), name="create-dispute"),
    path("hotspots/", views.hotspot_summary, name="hotspot-summary"),
    path("notaries/", views.notary_directory, name="notary-directory"),
    path("contracts/mine/", views.contracts_mine, name="contracts-mine"),
    path("contracts/<int:pk>/", views.update_contract, name="update-contract"),
    path("parcels/<int:pk>/documents/", views.parcel_documents, name="parcel-documents"),
    path("admin/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("audit/chain/", views.audit_chain, name="audit-chain"),
    path("audit/validate/", views.audit_validate, name="audit-validate"),
    path("admin/users/", views.admin_users, name="admin-users"),
    path("admin/users/<int:pk>/", views.admin_user_detail, name="admin-user-detail"),
]
