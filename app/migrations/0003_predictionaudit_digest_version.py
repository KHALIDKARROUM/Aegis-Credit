from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0002_product_workflows"),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionaudit",
            name="digest_version",
            field=models.CharField(default="legacy-sha256", max_length=24),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="predictionaudit",
            name="digest_version",
            field=models.CharField(default="hmac-sha256-v1", max_length=24),
        ),
    ]
