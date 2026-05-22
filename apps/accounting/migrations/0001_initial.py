# Generated for LedgerOS Epic 1 structured implementation.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Entity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Default Entity", max_length=255)),
                ("slug", models.SlugField(default="default", max_length=64, unique=True)),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=64)),
                ("record_type", models.CharField(max_length=128)),
                ("record_id", models.CharField(max_length=64)),
                ("source", models.CharField(default="system", max_length=64)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-timestamp", "-id"]},
        ),
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account_code", models.CharField(max_length=32)),
                ("name", models.CharField(max_length=255)),
                ("type", models.CharField(choices=[("asset", "Asset"), ("liability", "Liability"), ("equity", "Equity"), ("revenue", "Revenue"), ("expense", "Expense")], max_length=32)),
                ("normal_balance", models.CharField(choices=[("debit", "Debit"), ("credit", "Credit")], max_length=8)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="accounts", to="accounting.entity")),
            ],
            options={"ordering": ["account_code"]},
        ),
        migrations.CreateModel(
            name="AccountingPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("status", models.CharField(choices=[("open", "Open"), ("soft_closed", "Soft closed"), ("locked", "Locked")], default="open", max_length=16)),
                ("name", models.CharField(blank=True, max_length=128)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="periods", to="accounting.entity")),
            ],
            options={"ordering": ["start_date"]},
        ),
        migrations.CreateModel(
            name="JournalEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("posted", "Posted"), ("reversed", "Reversed")], default="draft", max_length=16)),
                ("source", models.CharField(default="manual", max_length=64)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("reversed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_journal_entries", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="journal_entries", to="accounting.entity")),
                ("period", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="journal_entries", to="accounting.accountingperiod")),
                ("reversal_of", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal_entries", to="accounting.journalentry")),
                ("reversed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversed_journal_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="JournalLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("side", models.CharField(choices=[("debit", "Debit"), ("credit", "Credit")], max_length=8)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lines", to="accounting.account")),
                ("journal_entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="accounting.journalentry")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(model_name="entity", constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("is_default",), name="one_default_entity")),
        migrations.AddConstraint(model_name="account", constraint=models.UniqueConstraint(fields=("entity", "account_code"), name="unique_account_code_per_entity")),
        migrations.AddConstraint(model_name="account", constraint=models.CheckConstraint(condition=models.Q(("normal_balance__in", ["debit", "credit"])), name="valid_account_normal_balance")),
        migrations.AddConstraint(model_name="accountingperiod", constraint=models.CheckConstraint(condition=models.Q(("start_date__lte", models.F("end_date"))), name="period_start_before_end")),
        migrations.AddConstraint(model_name="accountingperiod", constraint=models.UniqueConstraint(fields=("entity", "start_date", "end_date"), name="unique_period_dates_per_entity")),
        migrations.AddConstraint(model_name="journalline", constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="journal_line_positive_amount")),
    ]
