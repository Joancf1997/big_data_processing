#!/usr/bin/env python

import sys
import time
import json
import logging
import requests
from common import setup_topic
from argparse import ArgumentParser
from confluent_kafka import Producer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS



def fetch_data(influx_client, data_query, producer, topic_energy, topic_weather, key, interval, dry_run):
    while True:
        try:
            for query in data_query:
                if query["type"] == "Influx":
                    # InfluxDB query - Energy data
                    result = influx_client.query_api().query(query=query["query"])
                    msg = [record.values for table in result for record in table.records]
                    for row in msg: 
                        logging.debug(f"response influx obj: {row}")
                        payload = { 
                            "time_stamp": time.time() * 1000,
                            "id": row["ID"],
                            "value": row["_value"],
                            "place": row["place"],
                            "generation": row["generation"],
                            "type_gen": row["type_gen"]
                        }
                        if not dry_run:
                            producer.produce(topic_energy, key=key, value=str(json.dumps(payload)).encode("utf-8"))
                            producer.poll(0)
                else:
                    logging.debug(f"request weather")
                    # Weather API - Weather data:
                    response = requests.get(query["query"])

                    if response.status_code == 200:
                        msg = response.json()
                        msg_data = msg['current']
                        payload = { 
                            "time_stamp": time.time() * 1000,
                            "lat": msg["lat"],
                            "lon": msg["lon"],
                            "place": query["place"],
                            "temp": msg_data["temp"],
                            "dew_point": msg_data["dew_point"],
                            "uvi": msg_data["uvi"],
                            "clouds": msg_data["clouds"]
                        }
                        if not dry_run:
                            producer.produce(topic_weather, key=key, value=str(json.dumps(payload)).encode("utf-8"))
                            producer.poll(0)
                time.sleep(interval)
            
        except Exception as ex:
            logging.error(f"Failed to fetch data from InfluxDB: {ex}", exc_info=ex)

        

def main():
    parser = ArgumentParser(description='Kafka producer for JSON messages received from InfluxDB Cloud')
    parser.add_argument("--bootstrap-servers", default="localhost:29092", help="bootstrap servers", type=str)
    parser.add_argument('--influxurl', help="InfluxDB URL", required=True, type=str)
    parser.add_argument('--influxtoken', help="InfluxDB Token", required=True, type=str)
    parser.add_argument('--influxorg', help="InfluxDB Organization", required=True, type=str)
    parser.add_argument('--influxquery1', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--influxquery2', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--influxquery3', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--apiurl1', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--apiurl2', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--apiurl3', help="InfluxDB Query", required=True, type=str)
    parser.add_argument('--id1', help="InfluxDB Query", default="hydro_g", required=True, type=str)
    parser.add_argument('--id2', help="InfluxDB Query", default="solar_g", required=True, type=str)
    parser.add_argument('--id3', help="InfluxDB Query", default="mall_c", required=True, type=str)
    parser.add_argument('--id4', help="InfluxDB Query", default="mall_w",required=True, type=str)
    parser.add_argument('--id5', help="InfluxDB Query", default="solar_w", required=True, type=str)
    parser.add_argument('--id6', help="InfluxDB Query", default="hydro_w", required=True, type=str)
    parser.add_argument('--key', help="Key for the kafka broker", default=None, type=str)
    parser.add_argument('--interval', default=2, help='interval between API requests in seconds', type=int)
    parser.add_argument('--topic_energy', default='energy', help='topic name for energy', type=str)
    parser.add_argument('--topic_weather', default='weather', help='topic name for weather', type=str)
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
        setup_topic(args.topic_energy, bootstrap_servers=args.bootstrap_servers, retention_ms=600000,
                    num_partitions=args.num_partitions, replication_factor=args.replication_factor)
        producer = Producer({
            "bootstrap.servers": args.bootstrap_servers,
            "compression.type": "gzip",
            "acks": "1",
            "linger.ms": "100"
        })

    # Data consumption points
    influx_queries = [args.influxquery1, args.influxquery2, args.influxquery3]
    weather_apis = [args.apiurl1, args.apiurl2, args.apiurl3]

    data_query = [
        { "type": 'Influx', "query": influx_queries[0] },
        { "type": 'Weather', "query": weather_apis[0], "place": args.id4 },
        { "type": 'Influx', "query": influx_queries[1] },
        { "type": 'Weather', "query": weather_apis[1], "place": args.id5 },
        { "type": 'Influx', "query": influx_queries[2] },
        { "type": 'Weather', "query": weather_apis[2], "place": args.id6 },
    ]

    # Influx Client
    influx_client = InfluxDBClient(url=args.influxurl, token=args.influxtoken, org=args.influxorg)

    # Proceed to fetch data from each place 
    fetch_data(influx_client, data_query, producer, args.topic_energy, args.topic_weather, args.key, args.interval, args.dry_run)

if __name__ == "__main__":
    main()
