from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors import FlinkKafkaConsumer, FlinkKafkaProducer
from pyflink.common.serialization import SimpleStringSchema
import json

def process_message(message):
    data = json.loads(message)
    # Add your processing logic here
    return json.dumps(data)

def main():
    env = StreamExecutionEnvironment.get_execution_environment()

    kafka_consumer = FlinkKafkaConsumer(
        topics='data-topic',
        deserialization_schema=SimpleStringSchema(),
        properties={'bootstrap.servers': 'kafka:9092', 'group.id': 'flink-group'}
    )

    kafka_producer = FlinkKafkaProducer(
        topic='output-topic',
        serialization_schema=SimpleStringSchema(),
        producer_config={'bootstrap.servers': 'kafka:9092'}
    )

    stream = env.add_source(kafka_consumer).map(process_message)
    stream.add_sink(kafka_producer)

    env.execute('Flink Kafka Job')

if __name__ == '__main__':
    main()
