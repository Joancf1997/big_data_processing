# We start from the custom Docker image including Flink + PyFlink (here customizable via build arg)
# so we do not have to install much via pip install
ARG FLINK_IMAGE=fracorco/pyflink:1.18.1-scala_2.12-java11
FROM ${FLINK_IMAGE}

# Install dependencies (done first to reuse Docker cache), then copy Python source files
WORKDIR /app
COPY requirements.txt .
RUN pip install -U pip && \
    pip install -r requirements.txt
COPY . .

# We submit the Flink application on a configurable Flink cluster
# The cluster can be created using this very same image (as it is based on PyFlink).
# The default property values are set assuming the container is run with --network=host,
# so all required services are available on localhost at usual ports)
CMD flink run \
    -m ${PROCESSOR_JOBMANAGER:-localhost:8081} \
    -pyfs . \
    -py ${PROCESSOR_IMPLEMENTATION:-processor.py} \
    $PROCESSOR_ARGS
