# Roundcube image

`Dockerfile` builds boring-mailstack's Roundcube from the official image
(pinned by digest) plus:

- `composer.json` / `composer.lock`: the base image's own PHP packages plus
  RCMCardDAV, Roundav and the libraries of Kolab's calendar, at exactly the
  tested versions (`composer install` from the lock file).
- Kolab's calendar, libcalendaring and libkolab from Kolab's git at a pinned
  commit, with `patches/kolab/` applied and the Elastic styles compiled.
  Patches 1-6 are commits offered to Kolab (not merged yet; 6 is
  Kolab ticket T1337); `local-*` are ours only. Once Kolab's git carries one,
  move the pin past it and drop the patch (a patch that no longer applies
  fails the build).
- Roundav 3.2.0 with `patches/roundav/`: one commit, a setting
  `roundav_folder_count_property` (off by default) for exact expand arrows
  from a server's subfolder counts (offered upstream on Roundav
  issue #25). 3.2.0 took the rest of what we offered (our
  folder-creation fix; settings for login up front, session reuse and tree
  depth). Once upstream releases the count, drop the patch.
- `plugins/mailstack_cloudfiles`: hands RCMCardDAV's Nextcloud login to
  Roundav and the calendar, and turns on Roundav's login-up-front and
  session settings.
- `plugins/mailstack_darkmail`: HTML mail in dark mode (auto, invert, off).
- `mailstack-defaults.inc.php`, `carddav-config.inc.php`, and the start tasks
  `etc-config.sh` (the private etc/ config copied for Apache), `plugin-db.*`
  (calendar tables) and `db-owner.sh` (database owner and mode).

## Changing library or plugin versions

```bash
roundcube/update-composer-lock require -W nicofrand/roundav:<version>
roundcube/update-composer-lock update -W <vendor/package>
```

Then build, run `tests/demo/run.sh`, and commit both composer files.

## A new Roundcube base image

The lock file belongs to the base image's own `composer.json`. After changing
`ARG ROUNDCUBE_IMAGE` in the Dockerfile, start from the new image's
files and re-add ours with the same constraints:

```bash
img=roundcube/roundcubemail:<tag>@sha256:<digest>
docker run --rm --entrypoint cat "$img" /usr/src/roundcubemail/composer.json > roundcube/composer.json
docker run --rm --entrypoint cat "$img" /usr/src/roundcubemail/composer.lock > roundcube/composer.lock
roundcube/update-composer-lock require -W roundcube/carddav:5.1.4 \
    nicofrand/roundav:3.2.0 \
    pear/http_request2:~2.7.0 sabre/vobject:~4.5.1 caxy/php-htmldiff:~0.1 lolli42/finediff:~1.0.3
```
