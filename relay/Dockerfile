FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && echo "postfix postfix/mailname string mailstack.local" | debconf-set-selections \
 && echo "postfix postfix/main_mailer_type string 'No configuration'" | debconf-set-selections \
 && apt-get install -y --no-install-recommends \
      postfix \
      libsasl2-modules \
      ca-certificates \
      bash \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/mail-relay

ENTRYPOINT ["/usr/local/bin/mail-relay"]
