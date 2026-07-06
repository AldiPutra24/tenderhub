from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        profile = getattr(user, "vendor_profile", None)
        email_verified = getattr(profile, "email_verified", False)
        return f"{user.pk}{user.password}{user.last_login}{timestamp}{user.email}{email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
