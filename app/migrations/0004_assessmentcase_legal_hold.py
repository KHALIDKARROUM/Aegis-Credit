from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0003_predictionaudit_digest_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentcase",
            name="legal_hold",
            field=models.BooleanField(default=False),
        ),
    ]
