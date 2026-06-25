from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PredictionAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("feature_digest", models.CharField(max_length=64)),
                ("probability", models.FloatField()),
                ("threshold", models.FloatField()),
                ("risk_category", models.CharField(max_length=16)),
                ("decision", models.CharField(max_length=80)),
                ("model_version", models.CharField(max_length=32)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
