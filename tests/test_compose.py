import json
import os
from urllib.error import HTTPError
from urllib.request import urlopen

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_COMPOSE_TESTS") != "1", reason="requires running Compose services"
)


def test_own_database_is_accessible_and_other_database_is_denied():
    own_db = os.environ["DB_NAME"]
    other_db = os.environ["TEST_OTHER_DB_NAME"]
    assert own_db != other_db
    credentials = {
        "host": os.environ["DB_HOST"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "connect_timeout": 3,
    }

    with psycopg.connect(dbname=own_db, **credentials) as connection:
        assert connection.execute("SELECT current_database(), current_user").fetchone() == (
            own_db,
            credentials["user"],
        )
        assert connection.execute(
            "SELECT has_database_privilege(current_user, %s, 'CONNECT')", (other_db,)
        ).fetchone() == (False,)

    with pytest.raises(psycopg.OperationalError), psycopg.connect(dbname=other_db, **credentials):
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
