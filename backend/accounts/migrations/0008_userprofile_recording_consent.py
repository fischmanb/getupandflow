from django.db import migrations, models


def backfill_recording_consent(apps, schema_editor):
    """Existing clients who accepted the ToS (which covers recording) consent;
    rows with no recorded acceptance keep the field default (True). The field
    is later revocable per client. See the model comment on recording_consent.
    """
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.filter(terms_accepted_at__isnull=False).update(recording_consent=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_userprofile_working_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="recording_consent",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill_recording_consent, migrations.RunPython.noop),
    ]
