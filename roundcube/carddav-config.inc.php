<?php

// RCMCardDAV admin settings. Static and secret-free: there are no presets.
// Presets are global -- every Roundcube user gets every preset -- so a
// per-account preset with fixed credentials would hand one account's
// Nextcloud to all users (DECISIONS.md, 2026-10-05). Each user adds their
// own addressbook in Settings -> CardDAV instead.

// Users may add their own addressbooks (the only way in, without presets).
$prefs['_GLOBAL']['fixed'] = false;

// The plugin default, stated explicitly: CardDAV passwords are stored
// encrypted with the user's Roundcube/IMAP password. A changed mail password
// means re-entering the CardDAV password once.
$prefs['_GLOBAL']['pwstore_scheme'] = 'encrypted';

$prefs['_GLOBAL']['loglevel'] = \Psr\Log\LogLevel::WARNING;
$prefs['_GLOBAL']['loglevel_http'] = \Psr\Log\LogLevel::ERROR;
