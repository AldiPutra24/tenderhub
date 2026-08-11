from django.conf import settings

def turnstile(request):
    return {
        "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY,
    }

def site_root(request):
    scheme = request.scheme
    host = request.get_host()
    canonical = f"{scheme}://{host}{request.path}"
    return {
        "SITE_ROOT_URL": f"{scheme}://{host}",
        "CANONICAL_URL": canonical,
    }