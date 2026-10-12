#!/bin/sh
set -e
cd /var/www/html
exec php /usr/local/lib/mailstack-plugin-db.php
