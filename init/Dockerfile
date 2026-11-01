FROM stalwartlabs/cli:1.0.13@sha256:9a1e07307d6f890a193322c4b737fc0868405f0f8486a19922cbf362f43884fd AS stalwart-cli

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

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
