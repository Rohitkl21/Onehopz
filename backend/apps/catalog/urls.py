"""URL configuration for Catalog domain."""

from django.urls import re_path

from .views import CatalogItemDetailView, CatalogItemListCreateView, CategoryListView

app_name = "catalog"

urlpatterns = [
    re_path(r"^categories/?$", CategoryListView.as_view(), name="category-list"),
    re_path(r"^items/?$", CatalogItemListCreateView.as_view(), name="catalog-item-list-create"),
    re_path(
        r"^items/(?P<pk>[0-9a-f-]+)/?$", CatalogItemDetailView.as_view(), name="catalog-item-detail"
    ),
]
