from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections

from apps.monolith.catalog.management.commands import seed_demo
from apps.monolith.catalog.models import Company, Location, Membership, Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo_passwords(monkeypatch):
    owner = "fixture-owner-password"
    viewer = "fixture-viewer-password"
    monkeypatch.setenv("DEMO_OWNER_PASSWORD", owner)
    monkeypatch.setenv("DEMO_VIEWER_PASSWORD", viewer)
    return owner, viewer


def run_seed():
    output = StringIO()
    call_command("seed_demo", stdout=output)
    return output.getvalue()


def test_seed_creates_demo_once_and_preserves_passwords(monkeypatch, demo_passwords):
    output = run_seed()
    tenant = Tenant.objects.get()
    company = Company.objects.get(tenant=tenant)
    users = get_user_model().objects
    owner = users.get(username="demo-owner")
    viewer = users.get(username="demo-viewer")

    assert set(
        Membership.objects.filter(tenant=tenant).values_list("user__username", "role")
    ) == {
        (owner.username, "owner"),
        (viewer.username, "viewer"),
    }
    assert set(
        Location.objects.filter(company=company).values_list(
            "fake_external_place_id", flat=True
        )
    ) == {
        "fake_place_101",
        "fake_place_102",
    }
    assert all(not user.is_staff and not user.is_superuser for user in (owner, viewer))
    assert all(
        user.check_password(password)
        for user, password in zip((owner, viewer), demo_passwords)
    )
    assert all(password not in output for password in demo_passwords)
    assert f"company ID {company.pk}" in output

    monkeypatch.delenv("DEMO_OWNER_PASSWORD")
    monkeypatch.delenv("DEMO_VIEWER_PASSWORD")
    assert "already exists" in run_seed()
    assert (
        Tenant.objects.count(),
        Company.objects.count(),
        users.count(),
        Location.objects.count(),
    ) == (1, 1, 2, 2)
    assert list(users.order_by("username").values_list("password", flat=True)) == [
        owner.password,
        viewer.password,
    ]


def test_owner_username_conflict_keeps_existing_account_intact():
    users = get_user_model().objects
    account = users.create_user(username="demo-owner")

    with pytest.raises(CommandError, match="conflict"):
        run_seed()

    assert list(users.values_list("pk", flat=True)) == [account.pk]
    assert not Tenant.objects.exists()


def test_viewer_username_conflict_rolls_back_creation(demo_passwords):
    users = get_user_model().objects
    account = users.create_user(username="demo-viewer")

    with pytest.raises(CommandError, match="already in use"):
        run_seed()

    assert list(users.values_list("pk", flat=True)) == [account.pk]
    assert not Tenant.objects.exists()


def test_blank_password_fails_before_creating_demo(monkeypatch, demo_passwords):
    monkeypatch.setenv("DEMO_VIEWER_PASSWORD", "")
    with pytest.raises(CommandError, match="cannot be empty"):
        run_seed()
    assert not get_user_model().objects.exists()
    assert not Tenant.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_seed_creates_one_demo_on_postgresql(monkeypatch, demo_passwords):
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row-level concurrency")

    barrier = Barrier(2, timeout=10)
    make_password = seed_demo.make_password

    def synchronize_owner_insert(password):
        if password == demo_passwords[0]:
            barrier.wait()
        return make_password(password)

    def seed_in_thread():
        try:
            return run_seed()
        finally:
            connections.close_all()

    monkeypatch.setattr(seed_demo, "make_password", synchronize_owner_insert)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(lambda _: seed_in_thread(), range(2)))

    assert sum("Created Coffee Demo" in output for output in outputs) == 1
    assert sum("already exists" in output for output in outputs) == 1
    assert (
        Tenant.objects.count(),
        Company.objects.count(),
        Location.objects.count(),
        Membership.objects.count(),
    ) == (1, 1, 2, 2)
