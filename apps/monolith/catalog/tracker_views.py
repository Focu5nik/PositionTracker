import httpx2
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.monolith.tracker_client import TrackerResponseError, fetch_tracker_identity
from apps.monolith.tracker_tokens import issue_tracker_token
from apps.tracker_contract import MAX_TENANT_ID, WHOAMI_SCOPE

from .models import Membership


@never_cache
@require_safe
def get_tracker_identity(request: HttpRequest, tenant_id: int) -> JsonResponse:
    if not settings.TRACKER_ENABLE_DEV_WHOAMI:
        return JsonResponse({"detail": "Not found."}, status=404)
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    if (
        not 0 < tenant_id <= MAX_TENANT_ID
        or not Membership.objects.filter(
            user_id=request.user.pk, tenant_id=tenant_id
        ).exists()
    ):
        return JsonResponse({"detail": "Not found."}, status=404)

    try:
        token = issue_tracker_token(
            tenant_id=tenant_id,
            scopes=[WHOAMI_SCOPE],
            signing_key=settings.TRACKER_DEV_SIGNING_KEY,
        )
    except ValueError:
        return JsonResponse({"detail": "Tracker integration unavailable."}, status=503)

    try:
        identity = fetch_tracker_identity(
            settings.TRACKER_BASE_URL, token=token, tenant_id=tenant_id
        )
    except httpx2.TimeoutException:
        return JsonResponse({"detail": "Tracker request timed out."}, status=504)
    except httpx2.HTTPError, httpx2.InvalidURL, TrackerResponseError:
        return JsonResponse({"detail": "Tracker request failed."}, status=502)

    return JsonResponse(identity.model_dump())
