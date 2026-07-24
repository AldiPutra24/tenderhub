from django.conf import settings
from django.http import Http404

class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(settings, "CONTENT_SECURITY_POLICY", ""):
            response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)

        response.setdefault("Referrer-Policy", getattr(settings, "SECURE_REFERRER_POLICY", "same-origin"))
        return response

class AdminIPWhitelistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_prefix = f"/{settings.ADMIN_URL_PATH}/"

        if request.path.startswith(admin_prefix):

            ip = request.META.get("HTTP_CF_CONNECTING_IP")

            if not ip:
                forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
                if forwarded:
                    ip = forwarded.split(",")[0].strip()

            if not ip:
                ip = request.META.get("REMOTE_ADDR")

            if settings.ADMIN_ALLOWED_IPS and ip not in settings.ADMIN_ALLOWED_IPS:
                raise Http404()

        return self.get_response(request)