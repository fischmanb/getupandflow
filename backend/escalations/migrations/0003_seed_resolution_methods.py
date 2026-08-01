from django.db import migrations

from escalations.constants import seed_resolution_methods


def seed(apps, schema_editor):
    # Idempotent (get_or_create keyed on slug) — safe to replay, and it never
    # clobbers a name leadership has since edited in admin.
    seed_resolution_methods(apps.get_model("escalations", "ResolutionMethod"))


def unseed(apps, schema_editor):
    # Reverse deletes only the seeded slugs, leaving any leadership-added rows.
    from escalations.constants import DEFAULT_RESOLUTION_METHODS

    model = apps.get_model("escalations", "ResolutionMethod")
    model.objects.filter(slug__in=[s for s, _ in DEFAULT_RESOLUTION_METHODS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("escalations", "0002_resolutionmethod_escalation_archived_at_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
