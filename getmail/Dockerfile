FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl dnsutils iproute2 less netcat-openbsd procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir getmail6==6.20.1

WORKDIR /app

COPY entrypoint.sh folders.py handoff.py /app/

ENTRYPOINT ["/app/entrypoint.sh"]
