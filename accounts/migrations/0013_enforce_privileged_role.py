from django.db import migrations, models


def normalize_privileged_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        models.Q(is_staff=True) | models.Q(is_superuser=True)
    ).exclude(role="admin").update(role="admin")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_clear_domain_data_preserve_users"),
    ]

    operations = [
        migrations.RunPython(
            normalize_privileged_roles,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(role="admin")
                    | (
                        models.Q(is_staff=False)
                        & models.Q(is_superuser=False)
                    )
                ),
                name="accounts_user_privileged_role_valid",
            ),
        ),
    ]
