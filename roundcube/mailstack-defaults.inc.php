<?php
// boring-mailstack release defaults for Roundcube.
//
// The image includes /var/roundcube/config/*.php in name order, after its
// own settings; this file is installed there as zz-boring-mailstack.inc.php
// so it comes after the operator's etc/roundcube/config.inc.php. It only
// adds and fills in, it never overrides an operator's explicit choice:
//
// - Filters (managesieve), Contacts (carddav), cloud files (roundav) and
//   Calendar (calendar) are part of the product, so they are always
//   enabled, even when etc/ sets its own plugin list (v2's local config
//   lists managesieve but not carddav). They are put at the end, in this
//   order whatever etc/ lists: mailstack_cloudfiles before roundav and
//   calendar, which it hands the user's Nextcloud login from their Contacts
//   (CardDAV) account (it owns their Nextcloud settings).
//   mailstack_darkmail shows HTML mail dark in dark mode (users choose how
//   in Settings > Preferences > Displaying Messages).
// - Without an explicit managesieve_host, Filters talk to the IMAP server's
//   host on 4190 with STARTTLS, using the same TLS options as IMAP. Stalwart
//   serves ManageSieve there by default.

$mailstack_plugins = ['managesieve', 'carddav', 'mailstack_cloudfiles', 'roundav', 'calendar', 'mailstack_darkmail'];
$config['plugins'] = array_values(array_merge(
    array_diff((array) ($config['plugins'] ?? []), $mailstack_plugins), $mailstack_plugins));
unset($mailstack_plugins);

if (empty($config['managesieve_host'])) {
    $imap = $config['imap_host'];
    if (is_array($imap)) {
        $first = array_key_first($imap);
        $imap = is_string($first) ? $first : $imap[$first];
    }
    $host = parse_url(preg_match('#^[a-z]+://#i', $imap) ? $imap : "tcp://$imap", PHP_URL_HOST);
    if (!$host) {
        throw new RuntimeException("boring-mailstack: no host in imap_host ($imap) for managesieve_host; set managesieve_host");
    }
    $config['managesieve_host'] = 'tls://' . $host . ':4190';
    unset($imap, $first, $host);
}

if (!isset($config['managesieve_conn_options']) && isset($config['imap_conn_options'])) {
    $config['managesieve_conn_options'] = $config['imap_conn_options'];
}

// Webmail's special folders are Stalwart's own (by its names): Roundcube's
// defaults ('Sent', 'Junk', 'Trash') would make an ordinary folder of that
// name, e.g. one imported from a provider or an old client, look like the
// special one (seen 2026-10-11: an ordinary "Junk" next to "Junk Mail").
foreach (['drafts_mbox' => 'Drafts', 'sent_mbox' => 'Sent Items',
          'junk_mbox' => 'Junk Mail', 'trash_mbox' => 'Deleted Items'] as $key => $name) {
    if (!isset($config[$key])) {
        $config[$key] = $name;
    }
}
unset($key, $name);

// Kolab calendar (CalDAV): keep appointments up to 64 KB in full in the
// local cache. Kolab's default 0 (undocumented) fetches every displayed
// appointment from the server one by one: 30-45 s per view with a real
// Nextcloud calendar instead of ~2 s (measured 2026-10-06).
if (!isset($config['dav_cache_threshold'])) {
    $config['dav_cache_threshold'] = '64K';
}

// Kolab calendar (CalDAV): keep each calendar's rights and sharing for
// dav_cache_ttl instead of asking Nextcloud on every request (~0.3 s -> ~0.1 s
// per view, 2026-10-06). Opt-in upstream (our patch 5-kolab-folderinfo-cache).
if (!isset($config['dav_cache_folder_info'])) {
    $config['dav_cache_folder_info'] = true;
}

// Invitations and replies sent by the calendar (and tasks) get a copy in Sent,
// like any other mail (patch 6-kolab-itip-save-sent). Users can switch it off
// under Settings -> Preferences -> Calendar -> Event Invitations.
if (!isset($config['calendar_itip_save_sent'])) {
    $config['calendar_itip_save_sent'] = true;
}
