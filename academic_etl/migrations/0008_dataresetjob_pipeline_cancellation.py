from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic_etl", "0007_pipelinerun_lifecycle_db_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinerun",
            name="cancel_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pipelinerun",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("queued", "Queued"),
                    ("discovering", "Discovering"),
                    ("crawling", "Crawling"),
                    ("retrying", "Retrying"),
                    ("cancelling", "Cancelling"),
                    ("cancelled", "Cancelled"),
                    ("validating", "Validating"),
                    ("review", "Review"),
                    ("importing", "Importing"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DataResetJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("staging", "Staging"), ("production", "Production"), ("all", "All")], default="all", max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("cancelling", "Cancelling"), ("clearing", "Clearing"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("worker_pid", models.PositiveIntegerField(blank=True, null=True)),
                ("deleted_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
