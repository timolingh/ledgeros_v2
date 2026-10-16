from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting", "0010_alter_payment_account_help_text")]
    operations = [migrations.AddField(
        model_name="paymentapplication", name="journal_entry",
        field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name="payment_application", to="accounting.journalentry",
            help_text="Settlement journal; nullable for historical applications."),
    )]
