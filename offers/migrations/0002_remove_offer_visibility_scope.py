from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("offers", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE offers_offer "
                "DROP COLUMN IF EXISTS visibility_scope;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
