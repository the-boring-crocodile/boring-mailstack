# The Roundcube base image, pinned by digest: this line only
# (update-composer-lock and tests/unit/run.sh read it here).
ARG ROUNDCUBE_IMAGE=roundcube/roundcubemail:1.7.4-apache@sha256:1162705d5fa6514e6dc2eb71896c208fc3cae35b9cb49019ae23e3cbd9eab79b

# Kolab's calendar plugins (calendar, libcalendaring, libkolab) from Kolab's
# git at a pinned commit. The Packagist release 3.6.1 pins
# pear/http_request2 2.5, which has a security advisory; this commit requires
# the fixed 2.7. patches/kolab/1-6 are exactly the commits prepared for
# Kolab: category count without a PHP warning; SQLite
# schema install and upgrades; own folders when the DAV user differs from the
# Roundcube login; DAV cache options documented; optional folder-info cache
# (dav_cache_folder_info); optional copies of iTip messages in Sent
# (calendar_itip_save_sent). local-*: ours only (German label for 6).
FROM alpine/git:v2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS kolab
COPY patches/kolab/ /patches/
RUN git clone -q --filter=blob:none https://git.kolab.org/source/roundcubemail-plugins-kolab.git /k \
 && git -C /k checkout -q df6f30f6515f8246defccabf2d4f66412df860da \
 && git -C /k apply /patches/*.patch

FROM ${ROUNDCUBE_IMAGE} AS roundcube-base

# Kolab ships its Elastic styles as LESS only. Compile libkolab.css (which
# holds the calendar's styles too) against this Roundcube's own Elastic
# sources, as Kolab's README describes (lessc --relative-urls).
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS kolab-css
COPY --from=kolab /k/plugins/libkolab /build/plugins/libkolab
COPY --from=roundcube-base /usr/src/roundcubemail/skins/elastic /build/skins/elastic
RUN npm install -g --silent less@4.2.2 \
 && cd /build/plugins/libkolab/skins/elastic \
 && lessc --relative-urls libkolab.less libkolab.css \
 && lessc --relative-urls -x libkolab.less libkolab.min.css \
 && test -s libkolab.css && test -s libkolab.min.css

FROM roundcube-base

# The base image keeps the real source at /usr/src/roundcubemail and only
# copies it into /var/www/html at container start (docker-entrypoint.sh),
# since the stack never bind-mounts the docroot itself -- only the DB
# and config.inc.php. So the plugin has to be added here, not there.
WORKDIR /usr/src/roundcubemail

# PHP libraries and Composer-installed plugins, exactly as tested: the
# base image's own packages plus RCMCardDAV (Contacts), Roundav (cloud
# files) and the libraries Kolab's calendar plugins require. The versions
# are fixed by composer.lock, which is part of the release (and its
# manifest); change them with roundcube/update-composer-lock, then test and
# commit both files. roundcube/plugin-installer (allowed in composer.json)
# places carddav and roundav in plugins/; it only runs with
# COMPOSER_ALLOW_SUPERUSER=1, as Composer runs as root here (observed
# 2026-10-05: otherwise the plugins land in vendor/, where Roundcube does
# not look). The tests make the build fail instead of producing an image
# without them.
COPY --chmod=0644 composer.json composer.lock ./
RUN COMPOSER_ALLOW_SUPERUSER=1 composer install --no-interaction --no-dev --no-progress \
 && test -f plugins/carddav/carddav.php && test -f plugins/roundav/roundav.php

# Roundav 3.2.0 (Packagist) took our folder-creation fix, fixed the double
# decoding of "+"/"%xx", and has settings for what our hook did (login up
# front, Nextcloud's session kept; mailstack_cloudfiles turns them on) and
# for the tree depth. One patch left (patches/roundav/), offered upstream on
# Roundav issue #25: the roundav_folder_count_property setting
# (off by default) names a WebDAV property with each folder's subfolder
# count, read in the same request, for exact expand arrows.
# mailstack_cloudfiles sets it to Nextcloud's nc:contained-folder-count, and
# depth 1, only for a server that reports the counts. Applied exactly; drift
# fails the build.
COPY patches/roundav/ /tmp/roundav-patches/
RUN for p in /tmp/roundav-patches/*.patch; do patch -p1 --forward --fuzz=0 --no-backup-if-mismatch -d plugins/roundav < "$p" || exit 1; done \
 && rm -rf /tmp/roundav-patches

# Kolab's calendar with its CalDAV driver (libraries: composer.lock above).
COPY --from=kolab /k/plugins/calendar plugins/calendar
COPY --from=kolab /k/plugins/libcalendaring plugins/libcalendaring
COPY --from=kolab /k/plugins/libkolab plugins/libkolab
COPY --from=kolab-css /build/plugins/libkolab/skins/elastic/libkolab.css /build/plugins/libkolab/skins/elastic/libkolab.min.css plugins/libkolab/skins/elastic/

# Our glue: Roundav and the calendar use the Nextcloud login the user
# already gave RCMCardDAV (see the plugin itself).
COPY plugins/mailstack_cloudfiles plugins/mailstack_cloudfiles
# HTML mail in dark mode (see the plugin itself).
COPY plugins/mailstack_darkmail plugins/mailstack_darkmail
# Apache runs as www-data and must read them, whatever the modes in the
# build context (a tree or release unpacked with umask 0027 has 0640).
# Not COPY --chmod: the legacy builder applies it to the directory only.
RUN chmod -R u=rwX,go=rX plugins/mailstack_cloudfiles plugins/mailstack_darkmail

# Static admin settings, no presets and no secrets (see the file itself).
# 0644: Apache runs as www-data and must read it; the source file is private.
COPY --chmod=0644 carddav-config.inc.php plugins/carddav/config.inc.php

# Release defaults: Filters, Contacts, cloud files and Calendar always on,
# Filters pointed at Stalwart. Named zz-* so the image includes it after the
# operator's etc/roundcube/config.inc.php (see the file itself).
COPY --chmod=0644 mailstack-defaults.inc.php /var/roundcube/config/zz-boring-mailstack.inc.php

# The operator's etc/roundcube/config.inc.php is private on the host; this
# pre-setup task gives Apache a readable copy (root:www-data 0640).
COPY --chmod=0755 etc-config.sh /entrypoint-tasks/pre-setup/10-mailstack-etc-config

# Plugin tables (libkolab, calendar's CalDAV driver): created on first
# start and updated on later ones, before the owner fix below.
COPY --chmod=0644 plugin-db.php /usr/local/lib/mailstack-plugin-db.php
COPY --chmod=0755 plugin-db.sh /entrypoint-tasks/post-setup/40-mailstack-plugin-db

# The image creates its SQLite database root-owned and world-writable;
# this post-setup task hands it to www-data, mode 0600, on every start.
COPY --chmod=0755 db-owner.sh /entrypoint-tasks/post-setup/50-mailstack-db-owner

# WORKDIR above is also this image's runtime CWD unless reset -- and
# docker-entrypoint.sh derives INSTALLDIR from `pwd` at container start.
# Left pointed at /usr/src/roundcubemail, the entrypoint would update the
# source tree in place instead of copying it into /var/www/html, leaving
# the docroot empty. Hand it back to the base image's own default.
WORKDIR /var/www/html
