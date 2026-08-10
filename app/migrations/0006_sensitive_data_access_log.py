from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("app", "0005_encrypt_sensitive_case_data")]

    operations = [
        migrations.CreateModel(
            name="SensitiveDataAccessLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.CharField(max_length=64)),
                ("object_type", models.CharField(max_length=32)),
                ("object_id", models.CharField(max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sensitive_data_accesses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="sensitivedataaccesslog",
            index=models.Index(fields=["object_type", "object_id", "-created_at"], name="app_sensiti_object__941965_idx"),
        ),
    ]
