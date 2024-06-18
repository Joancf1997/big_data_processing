#!/usr/bin/env python

from time import sleep
from confluent_kafka.admin import AdminClient


def wait_for_topics(bootstrap_servers: str, *topics):
    client = AdminClient({"bootstrap.servers": bootstrap_servers})
    while True:
        existing_topics = client.list_topics().topics.keys()
        if all(t in existing_topics for t in topics):
            print(f"Found topics {topics}")
            return
        else:
            print(f"Waiting for topics {topics}")
            sleep(1.0)
