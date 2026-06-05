import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage


logger = logging.getLogger(__name__)


class ResilientCompressedManifestStaticFilesStorage(
    CompressedManifestStaticFilesStorage
):
    """
    Keep manifest hashing, but do not turn a stale manifest into an HTTP 500.

    The unhashed URL is only a fallback. A correct production deployment still
    runs collectstatic and serves fingerprinted, compressed assets.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reported_missing_entries = set()

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            clean_name = self.clean_name(name)
            if clean_name not in self._reported_missing_entries:
                logger.info(
                    "Static manifest entry missing for %s; using unhashed URL. "
                    "Run collectstatic and restart the application.",
                    clean_name,
                )
                self._reported_missing_entries.add(clean_name)
            return clean_name
