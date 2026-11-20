from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from apps.monolith.catalog.models import Company, Location, Membership, Tenant

pytestmark = pytest.mark.django_db
BROWSER_ACCEPT = "text/html,application/xhtml+xml,*/*;q=0.8"


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="reader")


@pytest.fixture
def locations():
    branches = []
    for name in ("Own", "Foreign"):
        tenant = Tenant.objects.create(name=name)
        company = Company.objects.create(tenant=tenant, name=name)
        branches.append(
            Location.objects.create(
                company=company,
                name=f"{name} branch",
                latitude=Decimal("55.755800"),
                longitude=Decimal("37.617600"),
                fake_external_place_id="fake_place_101",
            )
        )
    return branches


@pytest.fixture
def reader(user, locations):
    Membership.objects.create(
        user=user, tenant=locations[0].company.tenant, role=Membership.Role.VIEWER
    )
    client = APIClient()
    client.force_login(user)
    return client


def locations_url(company_id):
    return reverse("company-locations", args=[company_id])


def location_url(location_id):
    return reverse("location-detail", args=[location_id])


def test_lists_only_the_requested_company_locations(reader, locations):
    own, _ = locations
    another_company = Company.objects.create(
        tenant=own.company.tenant, name="Other company"
    )
    Location.objects.create(
        company=another_company,
        name="Other branch",
        latitude=0,
        longitude=0,
        fake_external_place_id="fake_place_other",
    )

    response = reader.get(locations_url(own.company_id))

    assert response.status_code == 200
    assert [location["id"] for location in response.json()] == [own.pk]


def test_reads_own_location_with_session(reader, locations):
    own, _ = locations
    response = reader.get(location_url(own.pk))

    assert response.status_code == 200
    assert response.json() == {
        "id": own.pk,
        "company_id": own.company_id,
        "name": own.name,
        "latitude": "55.755800",
        "longitude": "37.617600",
        "fake_external_place_id": own.fake_external_place_id,
        "version": 1,
        "is_active": True,
    }


def test_foreign_location_is_indistinguishable_from_missing(reader, locations):
    _, foreign = locations
    missing = reader.get(location_url(foreign.pk + 1))
    response = reader.get(
        location_url(foreign.pk), HTTP_X_TENANT_ID=str(foreign.company.tenant_id)
    )

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()


def test_foreign_company_locations_do_not_leak(reader, locations):
    _, foreign = locations
    missing = reader.get(locations_url(foreign.company_id + 1))
    response = reader.get(
        locations_url(foreign.company_id),
        {"tenant_id": foreign.company.tenant_id},
        HTTP_X_TENANT_ID=str(foreign.company.tenant_id),
    )

    assert response.status_code == missing.status_code == 200
    assert response.json() == missing.json() == []


def test_access_follows_current_memberships(reader, user, locations):
    own, foreign = locations
    membership = Membership.objects.create(
        user=user, tenant=foreign.company.tenant, role=Membership.Role.OWNER
    )
    assert reader.get(location_url(own.pk)).status_code == 200
    assert reader.get(location_url(foreign.pk)).status_code == 200

    membership.delete()
    assert reader.get(location_url(foreign.pk)).status_code == 404

    Membership.objects.filter(user=user).delete()
    assert reader.get(location_url(own.pk)).status_code == 404
    assert reader.get(locations_url(own.company_id)).json() == []


@pytest.mark.parametrize("url_name", ["company-locations", "location-detail"])
def test_anonymous_requests_require_authentication(url_name, locations):
    own, _ = locations
    pk = own.company_id if url_name == "company-locations" else own.pk
    response = APIClient().get(reverse(url_name, args=[pk]))

    assert response.status_code == 403


def test_browsable_api_sign_in_and_out_with_csrf(user, locations):
    own, _ = locations
    password = "fixture-password"
    user.set_password(password)
    user.save(update_fields=["password"])
    Membership.objects.create(
        user=user, tenant=own.company.tenant, role=Membership.Role.VIEWER
    )
    browser = Client(enforce_csrf_checks=True, headers={"Accept": BROWSER_ACCEPT})
    company_url = locations_url(own.company_id)
    login_url = f"{reverse('rest_framework:login')}?next={company_url}"
    logout_url = f"{reverse('rest_framework:logout')}?next={company_url}"

    anonymous = browser.get(company_url)
    assert anonymous.status_code == 403
    assert anonymous.headers["Content-Type"].startswith("text/html")
    assert login_url.encode() in anonymous.content

    form = browser.get(login_url)
    assert form.status_code == 200
    assert b'name="csrfmiddlewaretoken"' in form.content
    credentials = {"username": user.username, "password": password, "next": company_url}
    assert browser.post(login_url, credentials).status_code == 403
    csrf = form.cookies[settings.CSRF_COOKIE_NAME].value
    sign_in = browser.post(login_url, {**credentials, "csrfmiddlewaretoken": csrf})
    assert sign_in.status_code == 302
    assert sign_in.url == company_url

    for url in (company_url, location_url(own.pk)):
        html = browser.get(url)
        assert html.status_code == 200
        assert html.headers["Content-Type"].startswith("text/html")
        assert "Accept" in html.headers["Vary"]
        assert own.name.encode() in html.content
    assert logout_url.encode() in browser.get(company_url).content

    raw = browser.get(company_url, {"format": "json"})
    assert raw.headers["Content-Type"] == "application/json"
    assert [row["id"] for row in raw.json()] == [own.pk]

    assert browser.post(logout_url).status_code == 403
    csrf = browser.cookies[settings.CSRF_COOKIE_NAME].value
    sign_out = browser.post(logout_url, {"csrfmiddlewaretoken": csrf})
    assert sign_out.status_code == 302
    assert sign_out.url == company_url
    assert browser.get(company_url).status_code == 403


def test_browsable_api_keeps_foreign_locations_private(reader, locations):
    _, foreign = locations
    detail = reader.get(location_url(foreign.pk), HTTP_ACCEPT=BROWSER_ACCEPT)
    listing = reader.get(locations_url(foreign.company_id), HTTP_ACCEPT=BROWSER_ACCEPT)

    assert detail.status_code == 404
    assert listing.status_code == 200
    for response in (detail, listing):
        assert response.headers["Content-Type"].startswith("text/html")
        assert foreign.name.encode() not in response.content


def test_locations_api_is_read_only(reader, locations):
    own, _ = locations
    assert (
        reader.post(locations_url(own.company_id), {}, format="json").status_code == 405
    )
    assert (
        reader.patch(
            location_url(own.pk), {"name": "Changed"}, format="json"
        ).status_code
        == 405
    )


@pytest.mark.parametrize(("latitude", "longitude"), [(90, -180), (-90, 180)])
def test_coordinate_boundaries_are_valid(locations, latitude, longitude):
    own, _ = locations
    own.latitude = Decimal(latitude)
    own.longitude = Decimal(longitude)

    own.full_clean()
    own.save(update_fields=["latitude", "longitude"])
    own.refresh_from_db()

    assert (own.latitude, own.longitude) == (latitude, longitude)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", "90.000001"),
        ("latitude", "-90.000001"),
        ("longitude", "180.000001"),
        ("longitude", "-180.000001"),
    ],
)
def test_out_of_range_coordinates_are_rejected(locations, field, value):
    own, _ = locations
    setattr(own, field, Decimal(value))

    with pytest.raises(ValidationError) as error:
        own.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError), transaction.atomic():
        own.save(update_fields=[field])


def test_membership_is_unique_per_user_and_tenant(reader, user, locations):
    own, _ = locations
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(
            user=user, tenant=own.company.tenant, role=Membership.Role.OWNER
        )


def test_fake_place_id_is_unique_within_a_company(locations):
    own, _ = locations
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.create(
            company=own.company,
            name="Duplicate branch",
            latitude=0,
            longitude=0,
            fake_external_place_id=own.fake_external_place_id,
        )
