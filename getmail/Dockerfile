FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl dnsutils iproute2 less netcat-openbsd procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir getmail6==6.20.1

WORKDIR /app

COPY entrypoint.sh folders.py handoff.py /app/

ENTRYPOINT ["/app/entrypoint.sh"]
