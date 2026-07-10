from django.core.management.base import BaseCommand, CommandError

from tenders.services.spse_slug_mapping import default_mapping_path, sync_slug_mapping


class Command(BaseCommand):
    help = "Refresh tenders/data/lpse_slug_mapping.json from the SPSE Inaproc portal"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and compare slug data without writing lpse_slug_mapping.json",
        )
        parser.add_argument(
            "--no-update-existing",
            action="store_true",
            help="Only add new slugs, keep existing slug labels unchanged",
        )
        parser.add_argument(
            "--show-changes",
            action="store_true",
            help="Print added and updated slug details",
        )

    def handle(self, *args, **options):
        try:
            result = sync_slug_mapping(
                update_existing=not options["no_update_existing"],
                dry_run=options["dry_run"],
            )
        except Exception as exc:
            raise CommandError(f"Failed to sync SPSE slugs: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "SPSE slug sync finished: "
                f"existing={result['existing_count']} "
                f"discovered={result['discovered_count']} "
                f"added={len(result['added'])} "
                f"updated={len(result['updated'])} "
                f"final={result['final_count']} "
                f"file={default_mapping_path()}"
            )
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN: lpse_slug_mapping.json was not changed."))

        if options["show_changes"]:
            self.print_changes("ADDED", result["added"])
            self.print_changes("UPDATED", result["updated"])

    def print_changes(self, label, changes):
        if not changes:
            return
        self.stdout.write(label)
        for slug, value in changes.items():
            if isinstance(value, dict):
                self.stdout.write(f"- {slug}: {value['old']} -> {value['new']}")
            else:
                self.stdout.write(f"- {slug}: {value}")
