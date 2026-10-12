#!/bin/bash
set -eu

GENERATED=/etc/postfix/generated
SOURCE=/config

[ -f "$SOURCE/main.cf" ] || {
    echo "ERROR: missing generated main.cf" >&2
    exit 1
}

[ -f "$SOURCE/sender_relay" ] || {
    echo "ERROR: missing generated sender_relay" >&2
    exit 1
}

[ -f "$SOURCE/sasl_passwd" ] || {
    echo "ERROR: missing generated sasl_passwd" >&2
    exit 1
}

[ -f "$SOURCE/sender_access" ] || {
    echo "ERROR: missing generated sender_access" >&2
    exit 1
}

install -d -m 700 "$GENERATED"

install -m 600 "$SOURCE/main.cf" /etc/postfix/main.cf
install -m 600 "$SOURCE/sender_relay" "$GENERATED/sender_relay"
install -m 600 "$SOURCE/sasl_passwd" "$GENERATED/sasl_passwd"
install -m 600 "$SOURCE/sender_access" "$GENERATED/sender_access"

# Listen only on the dedicated Stalwart -> relay network.
# Do not rely on Docker interface numbering such as eth0/eth1.
PRIVATE_IP=$(
    getent ahostsv4 relay-private |
    awk 'NR == 1 { print $1 }'
)

[ -n "$PRIVATE_IP" ] || {
    echo "ERROR: unable to resolve private relay address" >&2
    exit 1
}

STALWART_IP=$(
    getent ahostsv4 stalwart-relay-client |
    awk 'NR == 1 { print $1 }'
)

[ -n "$STALWART_IP" ] || {
    echo "ERROR: unable to resolve Stalwart relay address" >&2
    exit 1
}

postconf -e "inet_interfaces = 127.0.0.1, $PRIVATE_IP"
postconf -e "mynetworks = 127.0.0.0/8 $STALWART_IP/32"

echo "MAIL RELAY START private_ip=$PRIVATE_IP stalwart_ip=$STALWART_IP"

install -d -m 755 /var/spool/postfix/etc
install -m 644 /etc/resolv.conf /var/spool/postfix/etc/resolv.conf

exec postfix start-fg
