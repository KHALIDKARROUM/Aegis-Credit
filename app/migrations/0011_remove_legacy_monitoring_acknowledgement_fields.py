# Generated manually because acknowledgements are immutable child events.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0010_batch_worker_leases"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="monitoringrun",
            name="acknowledged_at",
        ),
        migrations.RemoveField(
            model_name="monitoringrun",
            name="acknowledged_by",
        ),
    ]
