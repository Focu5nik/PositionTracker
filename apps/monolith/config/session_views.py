import json

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe


@never_cache
@require_safe
def csrf_token(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"csrfToken": get_token(request)})


@never_cache
@require_POST
def sign_in(request: HttpRequest) -> JsonResponse:
    if request.content_type != "application/json":
        return JsonResponse({"detail": "Expected application/json."}, status=415)

    try:
        data = json.loads(request.body)
    except (ValueError, RecursionError):
        return JsonResponse({"detail": "Invalid JSON."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"detail": "Expected a JSON object."}, status=400)
    username, password = data.get("username"), data.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not username
        or not password
    ):
        return JsonResponse(
            {"detail": "Username and password are required."}, status=400
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid credentials."}, status=403)

    login(request, user)
    return JsonResponse({"csrfToken": get_token(request)})


@never_cache
@require_POST
def sign_out(request: HttpRequest) -> HttpResponse:
    logout(request)
    return HttpResponse(status=204)
