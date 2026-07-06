from django.contrib.auth.backends import ModelBackend


class EmailVerifiedOrActiveBackend(ModelBackend):
    def user_can_authenticate(self, user):
        if user.is_active:
            return True
        profile = getattr(user, "vendor_profile", None)
        return bool(profile and profile.email_verified)
