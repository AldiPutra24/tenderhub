import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TurnstileService:
    @classmethod
    def verify(cls, token: str, ip: str | None = None) -> bool:
        if not token:
            return False

        secret = getattr(settings, "TURNSTILE_SECRET_KEY", None)

        if not secret:
            logger.error("TURNSTILE_SECRET_KEY is not configured.")
            return False

        payload = {
            "secret": secret,
            "response": token,
        }

        if ip:
            payload["remoteip"] = ip

        try:
            response = requests.post(
                settings.TURNSTILE_VERIFY_URL,
                data=payload,
                timeout=10,
            )

            response.raise_for_status()

            result = response.json()

            return bool(result.get("success"))

        except requests.RequestException:
            logger.exception("Cloudflare Turnstile verification failed.")
            return False