from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services.locations import LocationProviderError, get_provinces, get_regencies


@require_GET
def provinces_api(request):
    provinces, source = get_provinces()
    response = JsonResponse(provinces, safe=False)
    response["X-Location-Source"] = source
    return response


@require_GET
def regencies_api(request):
    province_id = request.GET.get("province_id", "").strip()
    if not province_id:
        return JsonResponse({"error": "province_id wajib diisi."}, status=400)

    try:
        regencies, source = get_regencies(province_id)
    except LocationProviderError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    response = JsonResponse(regencies, safe=False)
    response["X-Location-Source"] = source
    return response
