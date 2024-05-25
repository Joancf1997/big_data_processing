# Dockerfile for Flink with Python
FROM flink:latest

# Install Python dependencies
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    pip3 install apache-flink pyflink

COPY flink_job.py /flink-job/

CMD ["python3", "/flink-job/flink_job.py"]
