#!/bin/sh
# Pre-setup task (run as root by the image's entrypoint, before its setup
# includes /var/roundcube/config/*.php). The operator's config holds
# des_key and stays private on the host (etc/ is 0600/0700, checked by
# deploy); root reads it here and hands Apache (www-data) a copy it can
# read and nobody else can.
set -eu
src=/run/mailstack-etc/config.inc.php
[ -f "$src" ] || { echo "mailstack: $src missing (etc/roundcube/config.inc.php)" >&2; exit 1; }
install -o root -g www-data -m 0640 "$src" /var/roundcube/config/config.inc.php
echo "mailstack: etc/roundcube/config.inc.php installed (root:www-data 0640)"
