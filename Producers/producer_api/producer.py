
#!/usr/bin/env python

import sys
import logging
from argparse import ArgumentParser
from confluent_kafka import Producer
from common import setup_topic
import requests
import time

def main():

    # Parse command line options (call program with --help to see supported options)
    parser = ArgumentParser(description='Kafka producer for JSON messages received from OpenWeatherMap API')
    parser.add_argument("--bootstrap-servers", default="localhost:29092", help="bootstrap servers", type=str)
    parser.add_argument('--apiurl', help="OpenWeatherMap API URL", required=True, type=str)
    parser.add_argument('--key', help="Key for the kafka broker", required=True, type=str)
    parser.add_argument('--topic', help="Topic name for the kafka broker", default='energy_weather', type=str)
    parser.add_argument('--interval', default=3, help='interval between API requests in seconds', type=int)
    parser.add_argument('--num-partitions', default=1, help='# partitions (default 1)', type=int)
    parser.add_argument('--replication-factor', default=1, help='replication factor (default 1)', type=int)
    parser.add_argument("--dry-run", help="print to stdout instead of writing to Kafka", action="store_true")
    parser.add_argument("--log-level", dest="log_level", default="debug", type=str, help="log level (debug*|info|warn|error|fatal|critical, *=default")
    args = parser.parse_args()

    # Configure logging (log to stdout if it is a terminal, otherwise stderr so to allow feeding messages to downstream program with --dry-run)
    logging.basicConfig(
        level=logging.getLevelName(args.log_level.upper()),
        format="%(asctime)s (%(levelname).1s) %(message)s [%(threadName)s]",
        stream=sys.stdout if sys.stdout.isatty() else sys.stderr
    )

    # Setup topic(s) and create Kafka Producer (if not in dry_run mode)
    producer = None
    if not args.dry_run:
        # Non-dry-run mode: emit to Kafka topic using a Kafka producer (both initialized here)
        setup_topic(args.topic, bootstrap_servers=args.bootstrap_servers, retention_ms=600000,
                    num_partitions=args.num_partitions, replication_factor=args.replication_factor)
        producer = Producer({
            "bootstrap.servers": args.bootstrap_servers,
            "compression.type": "gzip",
            "acks": "1",
            "linger.ms": "100" # allow some batching
        })

    try:
        while True:
            response = requests.get(args.apiurl)
            if response.status_code == 200:
                msg = response.json()
                msg_data = msg['current']
                logging.debug(f"Received: {msg_data}")
                if not args.dry_run:
                    producer.produce(args.topic, key=args.key, value=str(msg_data).encode("utf-8"))
                    producer.poll(0)
            else:
                logging.error(f"Failed to fetch data from API: {response.status_code}")

            time.sleep(args.interval)

    except Exception as ex:
        logging.error(f"Error occurred: {ex}", exc_info=ex)
    finally:
        # Flush producer on non-dry-run mode
        if not args.dry_run: producer.flush(3.0)
        logging.info("Stopped")


if __name__ == "__main__":
    main()
