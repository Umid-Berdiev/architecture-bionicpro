"""DAG integrity test. Run inside the Airflow container:

    docker compose exec airflow-scheduler python -m pytest /opt/airflow/tests -q
"""
import os

from airflow.models import DagBag

DAGS = os.environ.get("AIRFLOW__CORE__DAGS_FOLDER", "/opt/airflow/dags")


def test_dag_loads_and_has_expected_pipeline():
    bag = DagBag(dag_folder=DAGS, include_examples=False)
    assert not bag.import_errors, bag.import_errors
    dag = bag.get_dag("bionicpro_reports_etl")
    assert dag is not None
    assert dag.schedule_interval == "@hourly"
    assert dag.catchup is False
    assert dag.max_active_runs == 1

    assert set(dag.task_ids) == {"extract_crm", "extract_telemetry", "build_mart", "update_watermark"}
    assert dag.get_task("extract_telemetry").upstream_task_ids == {"extract_crm"}
    assert dag.get_task("build_mart").upstream_task_ids == {"extract_telemetry"}
    assert dag.get_task("update_watermark").upstream_task_ids == {"build_mart"}
