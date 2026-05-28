from django.db import migrations, models


def soft_closed_to_closed(apps, schema_editor):
    AccountingPeriod = apps.get_model("accounting", "AccountingPeriod")
    AccountingPeriod.objects.filter(status="soft_closed").update(status="closed")

    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    try:
        journal_entry_ct = ContentType.objects.get(app_label="accounting", model="journalentry")
    except ContentType.DoesNotExist:
        return
    Permission.objects.filter(
        content_type=journal_entry_ct,
        codename="post_soft_closed_journal_entries",
    ).delete()


def closed_to_soft_closed(apps, schema_editor):
    AccountingPeriod = apps.get_model("accounting", "AccountingPeriod")
    AccountingPeriod.objects.filter(status="closed").update(status="soft_closed")


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0002_journalentry_soft_closed_permission"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(soft_closed_to_closed, closed_to_soft_closed),
        migrations.AlterField(
            model_name="accountingperiod",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("closed", "Closed"),
                    ("locked", "Locked"),
                ],
                default="open",
                max_length=16,
            ),
        ),
        migrations.AlterModelOptions(
            name="journalentry",
            options={"ordering": ["-date", "-id"]},
        ),
    ]
