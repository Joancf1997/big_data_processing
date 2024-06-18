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
    parser.add_argument("--topic", default="trades", help="Kafka topic name for input trades data", type=str)
    parser.add_argument("--db-url", default="jdbc:postgresql://localhost:25432/db", help="JDBC URL of output database", type=str)
    parser.add_argument("--db-username", default="user", help="username for accessing output database", type=str)
    parser.add_argument("--db-password", default="user", help="password for accessing output database", type=str)
    parser.add_argument("--dry-run", help="print to stdout instead of writing to DB", action="store_true")
    parser.add_argument("--ui-port", default=8081, help="enables Flink UI at specified port when running standalone (mini-cluster mode)")
    args = parser.parse_args()

    # Wait for input Kafka topic
    wait_for_topics(args.bootstrap_servers, args.topic)

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

    # Create a statement set where to collect all the SQL statements to run as a single job
    statements_to_execute = tenv.create_statement_set()

    # Define source table 'trades' reading from Kafka
    tenv.execute_sql(f"""
        CREATE TABLE `trades` (
            `exchange` VARCHAR,
            `base` VARCHAR,
            `quote` VARCHAR,
            `direction` VARCHAR,
            `price` DOUBLE,
            `volume` DOUBLE,
            `timestamp` BIGINT,
            `priceUsd` DOUBLE,
            `ts` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
            WATERMARK FOR `ts` AS `ts` - INTERVAL '1' SECOND
        ) WITH (
            'connector' = 'kafka',
            'topic' = '{args.topic}',
            'properties.bootstrap.servers' = '{args.bootstrap_servers}',
            'properties.group.id' = 'processor-python',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'json'
        )
        """)

    # Define sink table 'candlesticks' writing to PostgreSQL
    tenv.execute_sql(f"""
        CREATE TABLE `candlesticks` (
            `ts_start` TIMESTAMP(3),
            `ts_end` TIMESTAMP(3),
            `currency_pair` VARCHAR,
            `price_avg` DOUBLE,
            `price_open` DOUBLE,
            `price_min` DOUBLE,
            `price_max` DOUBLE,
            `price_close` DOUBLE,
            `volume` DOUBLE,
            `num_trades` INT,
            PRIMARY KEY (`ts_start`, `ts_end`, `currency_pair`) NOT ENFORCED
        ) WITH ( { get_output_connector_config(args, "candlesticks") } )
        """)

    # Define the query to populate table 'candlesticks'
    candlesticks_query = tenv.sql_query("""
        SELECT   `window_start` AS `ts_start`,
                 `window_end` AS `ts_end`,
                 `base` || ' / ' || `quote` AS `currency_pair`,
                 SUM(`price` * `volume`)  / SUM(`volume`) AS `price_avg`,
                 FIRST_VALUE(`price`) AS `price_open`,
                 MIN(`price`) AS `price_min`,
                 MAX(`price`) AS `price_max`,
                 LAST_VALUE(`price`) AS `price_close`,
                 SUM(`volume`) AS `volume`,
                 CAST(COUNT(*) AS INTEGER) AS `num_trades`
        FROM     TABLE(TUMBLE(TABLE `trades`, DESCRIPTOR(ts), INTERVAL '1' MINUTES))
        GROUP BY `base`, `quote`, `window_start`, `window_end`
        """)

    # Enqueue an INSERT statement to populate table 'candlesticks' with the corresponding query
    statements_to_execute.add_insert("candlesticks", candlesticks_query)

    # Define sink table 'volumes' writing to PostgreSQL
    tenv.execute_sql(f"""
        CREATE TABLE `volumes` (
            `ts_start` TIMESTAMP(3),
            `ts_end` TIMESTAMP(3),
            `currency_pair` VARCHAR,
            `volume_buy` DOUBLE,
            `volume_sell` DOUBLE,
            PRIMARY KEY (`ts_start`, `ts_end`, `currency_pair`) NOT ENFORCED
        ) WITH ( { get_output_connector_config(args, "volumes") } )
        """)

    # <BEGIN SOLUTION>

    # Define the query to populate table 'volumes'
    volumes_query: Table = tenv.sql_query("""
        SELECT   `window_start` AS `ts_start`,
                 `window_end` AS `ts_end`,
                 `base` || ' / ' || `quote` AS `currency_pair`,
                 SUM(CASE WHEN `direction` = 'buy' THEN `volume` ELSE 0 END) AS `volume_buy`,
                 SUM(CASE WHEN `direction` = 'sell' THEN `volume` ELSE 0 END) AS `volume_sell`
        FROM     TABLE(TUMBLE(TABLE `trades`, DESCRIPTOR(`ts`), INTERVAL '1' MINUTES))
        GROUP BY `base`, `quote`, `window_start`, `window_end`
        """)

    # Enqueue an INSERT statement to populate table 'volumes' with the corresponding query
    statements_to_execute.add_insert("volumes", volumes_query)

    # <END SOLUTION>

    # Execute all statements as a single job
    print(f"Submitting job: topic '{args.topic}' on '{args.bootstrap_servers}' -> '{args.db_url}'" +
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
