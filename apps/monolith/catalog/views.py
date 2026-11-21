from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.serializers import ModelSerializer

from .models import Location, Membership


class LocationSerializer(ModelSerializer):
    class Meta:
        model = Location
        fields = (
            "id",
            "company_id",
            "name",
            "latitude",
            "longitude",
            "fake_external_place_id",
            "version",
            "is_active",
        )
        read_only_fields = fields


class LocationReadView(GenericAPIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer)
    serializer_class = LocationSerializer

    def get_queryset(self) -> QuerySet[Location]:
        tenant_ids = Membership.objects.filter(user_id=self.request.user.pk).values(
            "tenant_id"
        )
        return Location.objects.filter(company__tenant_id__in=tenant_ids)


class CompanyLocationList(LocationReadView, ListAPIView):
    def get_queryset(self) -> QuerySet[Location]:
        return (
            super()
            .get_queryset()
            .filter(company_id=self.kwargs["company_id"])
            .order_by("pk")
        )


class LocationDetail(LocationReadView, RetrieveAPIView):
    pass
