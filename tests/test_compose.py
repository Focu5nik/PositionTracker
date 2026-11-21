import json
import os
import secrets
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import httpx2
import jwt
import psycopg
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.monolith.catalog.models import Membership, Tenant

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_COMPOSE_TESTS") != "1",
    reason="requires running Compose services",
)


@pytest.fixture
def db_credentials():
    prefix = "TRACKER_" if "TRACKER_DB_NAME" in os.environ else ""
    return {
        "dbname": os.environ[f"{prefix}DB_NAME"],
        "host": os.environ[f"{prefix}DB_HOST"],
        "user": os.environ[f"{prefix}DB_USER"],
        "password": os.environ[f"{prefix}DB_PASSWORD"],
        "connect_timeout": 3,
    }


def test_own_database_is_accessible_and_other_database_is_denied(db_credentials):
    own_db = db_credentials["dbname"]
    other_db = os.environ["TEST_OTHER_DB_NAME"]
    assert own_db != other_db

    with psycopg.connect(**db_credentials) as connection:
        assert connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone() == (
            own_db,
            db_credentials["user"],
        )
        assert connection.execute(
            "SELECT has_database_privilege(current_user, %s, 'CONNECT')", (other_db,)
        ).fetchone() == (False,)

    with (
        pytest.raises(psycopg.OperationalError),
        psycopg.connect(**{**db_credentials, "dbname": other_db}),
    ):
        pytest.fail("Application credentials connected to the other database")


@pytest.mark.parametrize("service", ["monolith", "tracker"])
@pytest.mark.parametrize("probe", ["live", "ready"])
def test_health_over_compose_dns(service, probe):
    with urlopen(f"http://{service}:8000/health/{probe}", timeout=5) as response:
        assert response.status == 200
        assert json.load(response) == {"status": probe}


def test_rabbitmq_management_is_available_and_requires_login():
    with urlopen("http://rabbitmq:15672/", timeout=5) as response:
        assert response.status == 200
    with pytest.raises(HTTPError) as failure:
        urlopen("http://rabbitmq:15672/api/overview", timeout=5)
    with failure.value as response:
        assert response.code == 401


@pytest.mark.skipif(
    "TRACKER_DB_NAME" not in os.environ, reason="runs in the Tracker container"
)
def test_tracker_alembic_revision_is_current(db_credentials):
    scripts = ScriptDirectory.from_config(Config(toml_file="pyproject.toml"))
    with psycopg.connect(**db_credentials) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall() == [
            (scripts.get_current_head(),),
        ]


@pytest.mark.skipif(
    "TRACKER_DB_NAME" not in os.environ, reason="runs in the Tracker container"
)
def test_tracker_dev_identity_over_http():
    url = "http://tracker:8000/internal/v1/whoami"
    if os.environ.get("TRACKER_ENABLE_DEV_WHOAMI") != "1":
        with pytest.raises(HTTPError) as failure:
            urlopen(url, timeout=5)
        with failure.value as response:
            assert response.code == 404
        return

    claims = {
        "iss": "positiontracker-dev",
        "aud": "positiontracker-tracker",
        "sub": "compose-smoke",
        "exp": int(time.time()) + 60,
        "tenant_id": 7,
        "scopes": ["tracker:whoami"],
    }
    token = jwt.encode(claims, os.environ["TRACKER_DEV_SIGNING_KEY"], algorithm="HS256")
    request = Request(
        url, headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "42"}
    )

    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert json.load(response) == {
            "service": claims["sub"],
            "tenant_id": claims["tenant_id"],
            "scopes": claims["scopes"],
            "database": os.environ["TRACKER_DB_NAME"],
        }


@pytest.mark.skipif(
    os.environ.get("DJANGO_SETTINGS_MODULE") != "apps.monolith.config.settings"
    or os.environ.get("TRACKER_ENABLE_DEV_WHOAMI") != "1",
    reason="requires the monolith Compose database and dev integration",
)
def test_monolith_issues_tracker_identity_after_browser_login(django_db_blocker):
    username = "compose-whoami-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    with django_db_blocker.unblock():
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=username, password=password
            )
            own = Tenant.objects.create(name=username)
            foreign = Tenant.objects.create(name=username + "-foreign")
            membership = Membership.objects.create(
                user=user, tenant=own, role=Membership.Role.VIEWER
            )
        try:
            own_url = f"/api/v1/tenants/{own.pk}/tracker/whoami"
            foreign_url = f"/api/v1/tenants/{foreign.pk}/tracker/whoami"
            with httpx2.Client(
                base_url="http://monolith:8000", timeout=5, trust_env=False
            ) as client:
                assert client.get(own_url).status_code == 403
                csrf = (
                    client.get("/api/v1/auth/csrf")
                    .raise_for_status()
                    .json()["csrfToken"]
                )
                login = client.post(
                    "/api/v1/auth/login",
                    headers={"X-CSRFToken": csrf},
                    json={"username": username, "password": password},
                )
                assert login.status_code == 200
                response = client.get(own_url, headers={"X-Tenant-ID": str(foreign.pk)})
                assert response.status_code == 200
                assert response.json() == {
                    "service": "positiontracker-monolith",
                    "tenant_id": own.pk,
                    "scopes": ["tracker:whoami"],
                    "database": os.environ["TEST_OTHER_DB_NAME"],
                }
                assert client.get(foreign_url).status_code == 404
                membership.delete()
                assert client.get(own_url).status_code == 404
                logout = client.post(
                    "/api/v1/auth/logout",
                    headers={"X-CSRFToken": login.json()["csrfToken"]},
                )
                assert logout.status_code == 204
        finally:
            with transaction.atomic():
                user.delete()
                Tenant.objects.filter(pk__in=[own.pk, foreign.pk]).delete()
