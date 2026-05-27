# Generated to gate soft-closed posting through an explicit permission.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="journalentry",
            options={
                "ordering": ["-date", "-id"],
                "permissions": [
                    (
                        "post_soft_closed_journal_entries",
                        "Can post journal entries in soft-closed periods",
                    )
                ],
            },
        ),
    ]
