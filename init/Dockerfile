FROM stalwartlabs/cli:1.0.13@sha256:9a1e07307d6f890a193322c4b737fc0868405f0f8486a19922cbf362f43884fd AS stalwart-cli

FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      dnsutils \
      iproute2 \
      less \
      netcat-openbsd \
      procps \
 && rm -rf /var/lib/apt/lists/*

COPY --from=stalwart-cli \
     /usr/local/bin/stalwart-cli \
     /usr/local/bin/stalwart-cli

RUN pip install --no-cache-dir PyYAML==6.0.3

WORKDIR /app

COPY init.sh /usr/local/bin/mailstack-init
RUN chmod 755 /usr/local/bin/mailstack-init

CMD ["/usr/local/bin/mailstack-init"]
