from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic_etl", "0005_alter_pipelinerun_seed_provider_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinerun",
            name="execution_state",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="retry_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="worker_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="worker_pid",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="worker_token",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
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
    ]
