from django.db import migrations, models
from django.db.migrations.operations.fields import AddField


class AddFieldIfNotExists(AddField):
    """Add the model state, but skip the database ALTER if the column exists."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        to_model = to_state.apps.get_model(app_label, self.model_name)
        table_name = to_model._meta.db_table
        field = to_model._meta.get_field(self.name)

        with schema_editor.connection.cursor() as cursor:
            existing_columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(
                    cursor,
                    table_name,
                )
            }

        if field.column in existing_columns:
            return

        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_remove_user_delivery_area"),
    ]

    operations = [
        AddFieldIfNotExists(
            model_name="user",
            name="avatar_url",
            field=models.URLField(blank=True, db_column="avatar"),
        ),
        AddFieldIfNotExists(
            model_name="user",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
        AddFieldIfNotExists(
            model_name="user",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        AddFieldIfNotExists(
            model_name="user",
            name="gender",
            field=models.CharField(blank=True, max_length=20),
        ),
        AddFieldIfNotExists(
            model_name="user",
            name="username_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
