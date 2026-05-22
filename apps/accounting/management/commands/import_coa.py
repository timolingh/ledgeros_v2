from django.core.management.base import BaseCommand

from apps.accounting.services.chart_import import import_chart_of_accounts


class Command(BaseCommand):
    help = "Import a YAML chart of accounts into the default entity."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to chart-of-accounts YAML file")

    def handle(self, *args, **options):
        result = import_chart_of_accounts(path=options["path"], source="management_command")
        self.stdout.write(
            self.style.SUCCESS(
                f"Chart of accounts imported: created={result.created}, updated={result.updated}, unchanged={result.unchanged}"
            )
        )
