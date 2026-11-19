from django.db import OperationalError, connection
from django.http import HttpRequest, JsonResponse


def live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "live"})


def check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def ready(request: HttpRequest) -> JsonResponse:
    try:
        check_database()
    except OperationalError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
