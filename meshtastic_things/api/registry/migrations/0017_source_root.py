from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0016_gateway_discovery"),
    ]

    operations = [
        migrations.RenameField(model_name="source", old_name="topic", new_name="root"),
    ]
