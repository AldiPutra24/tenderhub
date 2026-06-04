from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(settings, "CONTENT_SECURITY_POLICY", ""):
            response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)

        response.setdefault("Referrer-Policy", getattr(settings, "SECURE_REFERRER_POLICY", "same-origin"))
        return response
