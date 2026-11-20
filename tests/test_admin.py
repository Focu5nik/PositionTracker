import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.monolith.catalog.models import Company, Location, Membership, Tenant

pytestmark = pytest.mark.django_db


def test_superuser_can_sign_in_to_admin_and_add_a_branch():
    password = "fixture-password"
    user = get_user_model().objects.create_superuser(
        username="operator", password=password
    )
    tenant = Tenant.objects.create(name="Demo")
    company = Company.objects.create(name="Demo", tenant=tenant)
    browser = Client(enforce_csrf_checks=True)
    login_url = reverse("admin:login")
    index_url = reverse("admin:index")
    add_url = reverse("admin:catalog_location_add")

    assert browser.get(index_url).status_code == 302
    form = browser.get(login_url)
    assert form.status_code == 200
    credentials = {"username": user.username, "password": password, "next": index_url}
    assert browser.post(login_url, credentials).status_code == 403
    login = browser.post(
        login_url,
        {
            **credentials,
            "csrfmiddlewaretoken": form.cookies[settings.CSRF_COOKIE_NAME].value,
        },
    )
    assert login.status_code == 302
    index = browser.get(index_url)
    for model in ("tenant", "company", "location", "membership"):
        assert reverse(f"admin:catalog_{model}_changelist").encode() in index.content

    branch = {
        "company": company.pk,
        "name": "New branch",
        "latitude": "55.755800",
        "longitude": "37.617600",
        "fake_external_place_id": "fake_place_900",
        "version": "1",
        "is_active": "on",
        "_save": "Save",
    }
    assert browser.get(add_url).status_code == 200
    csrf = browser.cookies[settings.CSRF_COOKIE_NAME].value
    assert (
        browser.post(add_url, {**branch, "csrfmiddlewaretoken": csrf}).status_code
        == 302
    )
    assert Location.objects.filter(company=company, name="New branch").exists()


@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.VIEWER])
def test_tenant_role_does_not_grant_admin_access(client, role):
    user = get_user_model().objects.create_user(username="member")
    tenant = Tenant.objects.create(name="Own")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    client.force_login(user)

    response = client.get(reverse("admin:catalog_location_changelist"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))


def test_staff_requires_model_permissions(client):
    user = get_user_model().objects.create_user(username="staff", is_staff=True)
    client.force_login(user)
    changelist = reverse("admin:catalog_location_changelist")
    assert client.get(changelist).status_code == 403

    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="catalog", codename="view_location"
        )
    )
    assert client.get(changelist).status_code == 200
    assert client.get(reverse("admin:catalog_location_add")).status_code == 403
