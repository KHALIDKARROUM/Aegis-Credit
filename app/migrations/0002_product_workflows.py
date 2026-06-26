import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def populate_prediction_request_ids(apps, schema_editor):
    prediction_audit = apps.get_model("app", "PredictionAudit")
    for audit in prediction_audit.objects.filter(request_id__isnull=True).iterator():
        audit.request_id = uuid.uuid4()
        audit.save(update_fields=["request_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionaudit",
            name="actor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prediction_audits",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="predictionaudit",
            name="request_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(
            populate_prediction_request_ids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="predictionaudit",
            name="request_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="predictionaudit",
            name="source",
            field=models.CharField(default="web", max_length=16),
        ),
        migrations.CreateModel(
            name="AssessmentCase",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "request_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source", models.CharField(default="web", max_length=16)),
                (
                    "applicant_reference",
                    models.CharField(blank=True, db_index=True, max_length=80),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_review", "In review"),
                            ("referred", "Referred"),
                            ("cleared", "Cleared"),
                            ("closed", "Closed"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                ("application_data", models.JSONField(default=dict)),
                ("probability", models.FloatField()),
                ("threshold", models.FloatField()),
                ("risk_category", models.CharField(max_length=16)),
                ("screening_result", models.CharField(max_length=120)),
                ("recommendation", models.CharField(max_length=120)),
                ("model_version", models.CharField(max_length=32)),
                ("explanation_rows", models.JSONField(default=list)),
                ("explanation_method", models.CharField(blank=True, max_length=255)),
                ("warnings", models.JSONField(default=list)),
                ("reviewer_notes", models.TextField(blank=True)),
                (
                    "override_decision",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "No override"),
                            ("standard_review", "Continue with standard review"),
                            ("manual_review", "Refer for manual review"),
                            ("enhanced_review", "Refer for enhanced review"),
                        ],
                        max_length=32,
                    ),
                ),
                ("override_reason", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_assessment_cases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_assessment_cases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="BatchAssessment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("file_name", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "Processing"),
                            ("complete", "Complete"),
                            ("failed", "Failed"),
                        ],
                        default="processing",
                        max_length=16,
                    ),
                ),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("valid_rows", models.PositiveIntegerField(default=0)),
                ("invalid_rows", models.PositiveIntegerField(default=0)),
                ("results", models.JSONField(default=list)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="batch_assessments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmentcase",
            index=models.Index(
                fields=["status", "-created_at"],
                name="app_assessm_status_2b05d7_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="assessmentcase",
            index=models.Index(
                fields=["risk_category", "-created_at"],
                name="app_assessm_risk_ca_b5bda2_idx",
            ),
        ),
    ]
