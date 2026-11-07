FROM apache/airflow:2.9.3-python3.11
# clickhouse-connect is the only extra dependency of the ETL; pytest runs the DAG integrity test.
RUN pip install --no-cache-dir clickhouse-connect==0.8.17 pytest==8.3.3
