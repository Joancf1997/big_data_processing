#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser
from pyflink.common import Configuration
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment, EnvironmentSettings
from kafka_utils import wait_for_topics


def main():

    # Parse command line options (call program with --help to see supported options)
    parser = ArgumentParser(description="Flink processor reading trades from Kafka and emitting window statistics to PostgreSQL")
    parser.add_argument("--bootstrap-servers", default="localhost:29092", help="Kafka bootstrap servers", type=str)
    parser.add_argument("--topic_energy", default="energy", help="Kafka topic name for the energy data", type=str)
    parser.add_argument("--topic_weather", default="weather", help="Kafka topic name for the weather data", type=str)
    parser.add_argument("--db-url", default="jdbc:postgresql://localhost:25432/db", help="JDBC URL of output database", type=str)
    parser.add_argument("--db-username", default="user", help="username for accessing output database", type=str)
    parser.add_argument("--db-password", default="user", help="password for accessing output database", type=str)
    parser.add_argument("--dry-run", help="print to stdout instead of writing to DB", action="store_true")
    parser.add_argument("--ui-port", default=8081, help="enables Flink UI at specified port when running standalone (mini-cluster mode)")
    args = parser.parse_args()

    # Wait for input Kafka topic
    wait_for_topics(args.bootstrap_servers, args.topic_energy)
    wait_for_topics(args.bootstrap_servers, args.topic_weather)

    # Obtain and configure Flink streaming and table environments
    # Note: we supply extra configuration table.exec.source.idle-timeout=1000 (ms) that allow
    # having Flink parallelism > # Kafka partitions (Flink tasks of source table `trades` that
    # don't get a partition assigned are idle and do not produce watermarks halting downstream
    # processing, but with this setting we allow ignoring them after 1000ms of idleness)
    conf = Configuration() \
        .set_integer("rest.port", args.ui_port) \
        .set_integer("table.exec.source.idle-timeout", 1000)
    script_dir = Path(__file__).parent.resolve()
    env = StreamExecutionEnvironment.get_execution_environment(conf)
    env.add_jars(Path(script_dir, "flink-sql-connector-kafka-3.1.0-1.18.jar").as_uri())
    env.add_jars(Path(script_dir, "flink-connector-jdbc-3.1.2-1.18.jar").as_uri())
    env.add_jars(Path(script_dir, "postgresql-42.7.3.jar").as_uri())
    tenv = StreamTableEnvironment.create(env, EnvironmentSettings.Builder().with_configuration(conf).build())
    # t_env.get_config().set_local_timezone("America/Los_Angeles")

    # Create a statement set where to collect all the SQL statements to run as a single job
    statements_to_execute = tenv.create_statement_set()

    # ====================== ENERGY DATA ======================
    # Define source table 'energy_record' reading from Kafka (most granular data point)
    tenv.execute_sql(f"""
        CREATE TABLE `energy_record` (
            `time_stamp` BIGINT,
            `id` VARCHAR,
            `value` DOUBLE,
            `place` VARCHAR, 
            `generation` boolean,
            `type_gen` VARCHAR,
            `ts` AS TO_TIMESTAMP_LTZ(`time_stamp`, 3),
            WATERMARK FOR `ts` AS `ts` - INTERVAL '1' SECOND
        ) WITH (
            'connector' = 'kafka',
            'topic' = '{args.topic_energy}',
            'properties.bootstrap.servers' = '{args.bootstrap_servers}',
            'properties.group.id' = 'processor-python',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'json',
            'json.fail-on-missing-field' = 'false',
            'json.ignore-parse-errors' = 'true'
        )
    """)
    # Define sink table 'point_data' writing to PostgreSQL
    tenv.execute_sql(f"""
        CREATE TABLE `point_data` (
            `time_stamp` timestamp,
            `id` VARCHAR, 
            `place` VARCHAR,
            `generation` boolean,
            `type_gen` VARCHAR,
            `kwh` DOUBLE,
            PRIMARY KEY (`time_stamp`, `place`, `id`) NOT ENFORCED
        ) WITH ( { get_output_connector_config(args, "point_data") } )
    """)
    # Define the query to populate table 'point_data' - Detail info per point
    consumption_points = tenv.sql_query("""
        SELECT  `ts` AS `time_stamp`,
                `id` as id, 
                `place` as place,
                `generation` as generation,
                `type_gen` as type_gen,
                `value` as kwh
        FROM     TABLE(TUMBLE(TABLE `energy_record`, DESCRIPTOR(ts), INTERVAL '1' MINUTES))
    """)
    statements_to_execute.add_insert("point_data", consumption_points)     # Run query for point_data


    # ====================== WEATHER DATA ======================
    tenv.execute_sql(f"""
        CREATE TABLE `weather_record` (
            `time_stamp` BIGINT,
            `lat` DOUBLE,
            `lon` DOUBLE,
            `place` VARCHAR,
            `temp` DOUBLE, 
            `dew_point` DOUBLE,
            `uvi` DOUBLE,
            `clouds` DOUBLE,
            `ts` AS TO_TIMESTAMP_LTZ(`time_stamp`, 3),
            WATERMARK FOR `ts` AS `ts` - INTERVAL '1' SECOND
        ) WITH (
            'connector' = 'kafka',
            'topic' = '{args.topic_weather}',
            'properties.bootstrap.servers' = '{args.bootstrap_servers}',
            'properties.group.id' = 'processor-python',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'json',
            'json.fail-on-missing-field' = 'false',
            'json.ignore-parse-errors' = 'true'
        )
    """)
    # Define sink table 'weather_data' writing to PostgreSQL
    tenv.execute_sql(f"""
        CREATE TABLE `weather_data` (
            `time_stamp` TIMESTAMP,
            `place` VARCHAR,
            `temp` DOUBLE PRECISION, 
            `dew_point` DOUBLE PRECISION,
            `uvi` DOUBLE PRECISION,
            `clouds` DOUBLE PRECISION,
            PRIMARY KEY (`time_stamp`, `place`)  NOT ENFORCED
        ) WITH ( { get_output_connector_config(args, "weather_data") } )
    """)
    # Define the query to populate table 'weather_data' - Detail info per point
    weather_points = tenv.sql_query("""
        SELECT  `ts` AS `time_stamp`,
                `place` as place,
                `temp` as temp,
                `dew_point` as dew_point,
                `uvi` as uvi,
                `clouds` as clouds
        FROM     TABLE(TUMBLE(TABLE `weather_record`, DESCRIPTOR(ts), INTERVAL '1' MINUTES))
    """)
    statements_to_execute.add_insert("weather_data", weather_points)     # Run query for point_data




    # ====================== ANALYTICS ENERGY PRODUCED vs GENERATED ======================
    tenv.execute_sql(f"""
        CREATE TABLE `energy_analytics` (
            `hour_group` TIMESTAMP,
            `kwh_prod` DOUBLE PRECISION, 
            `kwh_cons` DOUBLE PRECISION,
            `ratio` DOUBLE PRECISION,
            PRIMARY KEY (`hour_group`)  NOT ENFORCED
        ) WITH ( { get_output_connector_config(args, "energy_analytics") } )
    """)
    energy_analysis_qry = tenv.sql_query("""
        SELECT 
            TUMBLE_START(`ts`, INTERVAL '10' MINUTE) AS hour_group,
            SUM(CASE WHEN `generation` THEN `value` ELSE 0 END) AS kwh_prod,
            SUM(CASE WHEN NOT generation THEN `value` ELSE 0 END) AS kwh_cons,
            CASE 
                WHEN SUM(CASE WHEN NOT `generation` THEN `value` ELSE 0 END) = 0 
                THEN NULL 
                ELSE SUM(CASE WHEN `generation` THEN `value` ELSE 0 END) / SUM(CASE WHEN NOT `generation` THEN `value` ELSE 0 END) 
            END AS ratio
        FROM `energy_record`
        GROUP BY TUMBLE(`ts`, INTERVAL '10' MINUTE);
    """)
    statements_to_execute.add_insert("energy_analytics", energy_analysis_qry) 

    # ====================== ANALYTICS ENERGY VS WEATHER ======================
    tenv.execute_sql(f"""
    CREATE TABLE `energy_weather_analytics` (
            `hour_group` TIMESTAMP,
            `place` VARCHAR,
            `kwh_cons_degree` DOUBLE,
            `kwh_prod_with_rain_prob` DOUBLE,
            `kwh_prod_with_no_rain_prob` DOUBLE,
            PRIMARY KEY (`hour_group`) NOT ENFORCED
        ) WITH ({get_output_connector_config(args, "energy_weather_analytics")})
    """)
    # Create the energy windowed table
    tenv.execute_sql(f"""
        CREATE VIEW `energy_window` AS
        SELECT 
            TUMBLE_START(`ts`, INTERVAL '10' MINUTE) AS window_start,
            `place` as place,
            SUM(CASE WHEN `generation` THEN `value` ELSE 0 END) AS kwh_prod,
            SUM(CASE WHEN NOT `generation` THEN `value` ELSE 0 END) AS kwh_cons
        FROM 
            `energy_record`
        GROUP BY 
            TUMBLE(`ts`, INTERVAL '10' MINUTE), `place`
    """)

    # Create the weather windowed table
    tenv.execute_sql(f"""
        CREATE VIEW weather_window AS
        SELECT 
            TUMBLE_START(ts, INTERVAL '10' MINUTE) AS window_start,
            place,
            AVG(temp) AS temp,
            AVG(dew_point) AS dew_point,
            CASE 
                WHEN (AVG(`temp`) - AVG(`dew_point`)) <= 0 THEN 'Rain' 
                ELSE 'No Rain'
            END AS raining_prob,
            AVG(`dew_point`) AS dew_point,
            AVG(uvi) AS uvi,
            AVG(clouds) AS clouds
        FROM 
            weather_record
        GROUP BY 
            TUMBLE(ts, INTERVAL '10' MINUTE), place
    """)

    # Final query joining the windowed tables
    energy_weather_analysis_qry = tenv.sql_query("""
        SELECT 
            e.window_start AS hour_group,
            e.place AS place,
            (AVG(e.kwh_cons) / AVG(w.temp)) AS kwh_cons_degree,
            SUM(CASE WHEN raining_prob = 'Rain' THEN kwh_prod ELSE 0 END) AS kwh_prod_with_rain_prob,
            SUM(CASE WHEN NOT raining_prob = 'Rain' THEN kwh_prod ELSE 0 END) AS kwh_prod_with_no_rain_prob,
            AVG(temp) AS temp,
            AVG(dew_point) AS dew_point,
            AVG(uvi) AS uvi,
            AVG(clouds) AS clouds
        FROM energy_window e
        JOIN weather_window w
        ON e.place = w.place AND e.window_start = w.window_start
        GROUP BY e.window_start, e.place
    """)

    statements_to_execute.add_insert("energy_weather_analytics", energy_weather_analysis_qry) 







    # Execute all statements as a single job
    print(f"Submitting job: topic '{args.topic_energy}' on '{args.bootstrap_servers}' -> '{args.db_url}'" +
        (" (dry-run)" if args.dry_run else ""))
    statements_to_execute.execute().wait()


def get_output_connector_config(args, table):
    if args.dry_run:
        # On dry-run mode, print to stdout, including table name as prefix
        return f"""
            'connector' = 'print',
            'print-identifier' = '{table}'
            """
    else:
        # Otherwise, write data to corresponding DB table using JDBC connector
        return f"""
            'connector' = 'jdbc',
            'table-name' = '{table}',
            'url' = '{args.db_url}',
            'username' = '{args.db_username}',
            'password' = '{args.db_password}'
            """


if __name__ == "__main__":
    main()
