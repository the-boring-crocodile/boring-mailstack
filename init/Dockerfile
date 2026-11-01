FROM stalwartlabs/cli:1.0.14@sha256:5b70732cb69cdab3ff0894c501544cf0bfa180fa75bcd0eeba4eebe04c1064e1 AS stalwart-cli

FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913

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
