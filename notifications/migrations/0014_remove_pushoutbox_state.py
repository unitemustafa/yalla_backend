from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0013_push_outbox"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="PushOutbox"),
            ],
        ),
    ]
