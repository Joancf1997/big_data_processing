#!/usr/bin/env python

import sys
import logging
from argparse import ArgumentParser
from confluent_kafka import Producer
from common import setup_topic
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import time


def fetch_data(influx_client, query, producer, topic, key, interval, dry_run):
    while True:
        try:
            result = influx_client.query_api().query(query=query)
            msg = [record.values for table in result for record in table.records]
            if len(msg) > 0:
                msg_data = msg[0]
            else : 
                msg_data = msg
            logging.debug(f"Received: {msg_data}")
            if not dry_run:
                producer.produce(topic, key=key, value=str(msg_data).encode("utf-8"))
                producer.poll(0)
        except Exception as ex:
            logging.error(f"Failed to fetch data from InfluxDB: {ex}", exc_info=ex)

        time.sleep(interval)

def main():
    parser = ArgumentParser(description='Kafka producer for JSON messages received from InfluxDB Cloud')
    parser.add_argument("--bootstrap-servers", default="localhost:29092", help="bootstrap servers", type=str)
    parser.add_argument('--influxurl', help="InfluxDB URL", required=True, type=str)
    parser.add_argument('--influxtoken', help="InfluxDB Token", required=True, type=str)
    parser.add_argument('--influxorg', help="InfluxDB Organization", required=True, type=str)
    parser.add_argument('--influxquery', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--key', help="Key for the kafka broker", required=True, type=str)
    parser.add_argument('--interval', default=3, help='interval between API requests in seconds', type=int)
    parser.add_argument('--topic', default='weather', help='topic name', type=str)
    parser.add_argument('--num-partitions', default=1, help='# partitions (default 1)', type=int)
    parser.add_argument('--replication-factor', default=1, help='replication factor (default 1)', type=int)
    parser.add_argument("--dry-run", help="print to stdout instead of writing to Kafka", action="store_true")
    parser.add_argument("--log-level", dest="log_level", default="debug", type=str, help="log level (debug*|info|warn|error|fatal|critical, *=default")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.getLevelName(args.log_level.upper()),
        format="%(asctime)s (%(levelname).1s) %(message)s [%(threadName)s]",
        stream=sys.stdout if sys.stdout.isatty() else sys.stderr
    )

    producer = None
    if not args.dry_run:
        setup_topic(args.topic, bootstrap_servers=args.bootstrap_servers, retention_ms=600000,
                    num_partitions=args.num_partitions, replication_factor=args.replication_factor)
        producer = Producer({
            "bootstrap.servers": args.bootstrap_servers,
            "compression.type": "gzip",
            "acks": "1",
            "linger.ms": "100"
        })

    influx_client = InfluxDBClient(url=args.influxurl, token=args.influxtoken, org=args.influxorg)
    fetch_data(influx_client, args.influxquery, producer, args.topic, args.key, args.interval, args.dry_run)

if __name__ == "__main__":
    main()
