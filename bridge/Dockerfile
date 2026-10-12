FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c

RUN mkdir -p /config

WORKDIR /app

COPY bridge.py /app/bridge.py

CMD ["python3", "/app/bridge.py"]
