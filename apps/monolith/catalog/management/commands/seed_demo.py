import os
import warnings
from decimal import Decimal
from getpass import GetPassWarning, getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Company, Location, Membership, Tenant

DEMO_NAME = "Coffee Demo"
OWNER_USERNAME = "demo-owner"
VIEWER_USERNAME = "demo-viewer"
BRANCHES = (
    ("Coffee Demo 101", "55.755800", "37.617600", "fake_place_101"),
    ("Coffee Demo 102", "55.764500", "37.605600", "fake_place_102"),
)


def read_password(variable: str, username: str) -> str:
    password = os.environ.get(variable)
    if password is None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            try:
                password = getpass(f"Password for {username}: ")
            except EOFError, GetPassWarning:
                raise CommandError(
                    f"Set {variable} or run with an interactive terminal."
                ) from None
    if not password:
        raise CommandError(f"Password for {username} cannot be empty.")
    return password


class Command(BaseCommand):
    help = "Create the Coffee Demo tenant, two users and two branches."
    requires_migrations_checks = True

    def handle(self, *args: object, **options: object) -> None:
        users = get_user_model().objects
        if users.filter(username=OWNER_USERNAME).exists():
            self.report_existing()
            return

        owner_password = read_password("DEMO_OWNER_PASSWORD", OWNER_USERNAME)
        viewer_password = read_password("DEMO_VIEWER_PASSWORD", VIEWER_USERNAME)
        with transaction.atomic():
            owner, created = users.get_or_create(
                username=OWNER_USERNAME,
                defaults={"password": lambda: make_password(owner_password)},
            )
            if not created:
                self.report_existing()
                return

            viewer, created = users.get_or_create(
                username=VIEWER_USERNAME,
                defaults={"password": lambda: make_password(viewer_password)},
            )
            if not created:
                raise CommandError(f"Username {VIEWER_USERNAME} is already in use.")

            tenant = Tenant.objects.create(name=DEMO_NAME)
            company = Company.objects.create(tenant=tenant, name=DEMO_NAME)
            Membership.objects.create(
                user=owner, tenant=tenant, role=Membership.Role.OWNER
            )
            Membership.objects.create(
                user=viewer, tenant=tenant, role=Membership.Role.VIEWER
            )
            for name, latitude, longitude, place_id in BRANCHES:
                Location.objects.create(
                    company=company,
                    name=name,
                    latitude=Decimal(latitude),
                    longitude=Decimal(longitude),
                    fake_external_place_id=place_id,
                )

        self.stdout.write(
            f"Created Coffee Demo (company ID {company.pk}): {OWNER_USERNAME}, {VIEWER_USERNAME}."
        )

    def report_existing(self) -> None:
        try:
            owner = Membership.objects.select_related("tenant").get(
                user__username=OWNER_USERNAME,
                tenant__name=DEMO_NAME,
                role=Membership.Role.OWNER,
            )
            Membership.objects.get(
                user__username=VIEWER_USERNAME,
                tenant=owner.tenant,
                role=Membership.Role.VIEWER,
            )
            company = Company.objects.get(tenant=owner.tenant, name=DEMO_NAME)
        except ObjectDoesNotExist, MultipleObjectsReturned:
            raise CommandError(
                "Existing demo usernames conflict with the Coffee Demo data."
            ) from None

        place_ids = {place_id for _, _, _, place_id in BRANCHES}
        if Location.objects.filter(
            company=company, fake_external_place_id__in=place_ids
        ).count() != len(place_ids):
            raise CommandError(
                "Coffee Demo already exists with incomplete branch data."
            )
        self.stdout.write(f"Coffee Demo already exists (company ID {company.pk}).")
