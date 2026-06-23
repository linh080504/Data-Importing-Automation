from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic_etl", "0006_pipelinerun_execution_lifecycle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pipelinerun",
            name="execution_state",
            field=models.JSONField(blank=True, db_default={}, default=dict),
        ),
        migrations.AlterField(
            model_name="pipelinerun",
            name="retry_count",
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
        migrations.AlterField(
            model_name="pipelinerun",
            name="worker_token",
            field=models.CharField(
                blank=True,
                db_default="",
                db_index=True,
                default="",
                max_length=64,
            ),
        ),
    ]
