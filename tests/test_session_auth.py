import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.monolith.catalog.models import Company, Location, Membership, Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    password = "fixture-password"
    user = get_user_model().objects.create_user(username="reader", password=password)
    return user, {"username": user.username, "password": password}


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True, headers={"Host": "localhost"})


def issue_csrf(browser):
    response = browser.get(reverse("auth-csrf"))
    assert response.status_code == 200
    assert settings.CSRF_COOKIE_NAME in response.cookies
    assert "no-store" in response.headers["Cache-Control"]
    return response.json()["csrfToken"]


def post_login(browser, credentials, **headers):
    return browser.post(
        reverse("auth-login"), credentials, content_type="application/json", **headers
    )


def test_login_rotates_csrf_and_session_allows_reading_until_logout(browser, account):
    user, credentials = account
    tenant = Tenant.objects.create(name="Own")
    company = Company.objects.create(tenant=tenant, name="Company")
    location = Location.objects.create(
        company=company,
        name="Branch",
        latitude=0,
        longitude=0,
        fake_external_place_id="fake_place_101",
    )
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.VIEWER)
    detail = reverse("location-detail", args=[location.pk])
    pre_login_token = issue_csrf(browser)
    previous_cookie = browser.cookies[settings.CSRF_COOKIE_NAME].value

    login = post_login(browser, credentials, HTTP_X_CSRFTOKEN=pre_login_token)

    assert login.status_code == 200
    assert login.cookies[settings.SESSION_COOKIE_NAME]["httponly"]
    assert login.cookies[settings.CSRF_COOKIE_NAME].value != previous_cookie
    assert browser.get(detail).status_code == 200

    logout = reverse("auth-logout")
    assert browser.post(logout).status_code == 403
    assert browser.post(logout, HTTP_X_CSRFTOKEN=pre_login_token).status_code == 403
    assert browser.get(detail).status_code == 200
    assert (
        browser.post(logout, HTTP_X_CSRFTOKEN=login.json()["csrfToken"]).status_code
        == 204
    )
    assert browser.get(detail).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"HTTP_X_CSRFTOKEN": "incorrect"}])
def test_login_requires_csrf_even_before_authentication(browser, account, headers):
    _, credentials = account
    issue_csrf(browser)

    assert post_login(browser, credentials, **headers).status_code == 403
    assert settings.SESSION_COOKIE_NAME not in browser.cookies


def test_login_rejects_cross_origin_post_with_valid_token(browser, account):
    _, credentials = account
    token = issue_csrf(browser)
    response = post_login(
        browser,
        credentials,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="https://untrusted.example",
    )
    assert response.status_code == 403
    assert settings.SESSION_COOKIE_NAME not in browser.cookies


def test_invalid_credentials_do_not_create_session(browser, account):
    _, credentials = account
    credentials["password"] = "incorrect"

    response = post_login(browser, credentials, HTTP_X_CSRFTOKEN=issue_csrf(browser))

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid credentials."}
    assert settings.SESSION_COOKIE_NAME not in browser.cookies


@pytest.mark.parametrize("body", ["{", "[]", {"username": "reader", "password": False}])
def test_login_rejects_invalid_json_or_fields(browser, body):
    response = post_login(browser, body, HTTP_X_CSRFTOKEN=issue_csrf(browser))
    assert response.status_code == 400


def test_auth_routes_restrict_http_methods(browser):
    token = issue_csrf(browser)
    assert browser.post(reverse("auth-csrf"), HTTP_X_CSRFTOKEN=token).status_code == 405
    assert browser.get(reverse("auth-login")).status_code == 405
    assert browser.get(reverse("auth-logout")).status_code == 405
