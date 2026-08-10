from django.db import migrations

import app.fields


def reencrypt_existing_values(apps, schema_editor):
    """Read legacy JSON/text values and re-save them through encrypted fields."""
    AssessmentCase = apps.get_model("app", "AssessmentCase")
    BatchAssessment = apps.get_model("app", "BatchAssessment")
    for case in AssessmentCase.objects.all().iterator():
        case.save(
            update_fields=[
                "application_data",
                "explanation_rows",
                "reviewer_notes",
                "warnings",
                "override_reason",
            ]
        )
    for batch in BatchAssessment.objects.all().iterator():
        batch.save(update_fields=["results"])


class Migration(migrations.Migration):
    dependencies = [("app", "0004_assessmentcase_legal_hold")]

    operations = [
        migrations.AlterField(
            model_name="assessmentcase",
            name="application_data",
            field=app.fields.EncryptedJSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="assessmentcase",
            name="explanation_rows",
            field=app.fields.EncryptedJSONField(default=list),
        ),
        migrations.AlterField(
            model_name="assessmentcase",
            name="reviewer_notes",
            field=app.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="assessmentcase",
            name="warnings",
            field=app.fields.EncryptedJSONField(default=list),
        ),
        migrations.AlterField(
            model_name="assessmentcase",
            name="override_reason",
            field=app.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="batchassessment",
            name="results",
            field=app.fields.EncryptedJSONField(default=list),
        ),
        migrations.RunPython(reencrypt_existing_values, migrations.RunPython.noop),
    ]
