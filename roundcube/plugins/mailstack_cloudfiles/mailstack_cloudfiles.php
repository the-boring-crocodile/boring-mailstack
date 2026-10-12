<?php
/**
 * boring-mailstack: Nextcloud files for Roundav, from the user's CardDAV account.
 *
 * A user who added a Nextcloud addressbook (RCMCardDAV) already gave Roundcube
 * a Nextcloud login: server, user name and (encrypted) app password. This
 * plugin hands exactly that to Roundav for each request, in memory only:
 *
 *   driver_webdav_url      https://<nextcloud host>/
 *   driver_webdav_prefix   [/<subpath>]/remote.php/dav/files/<Nextcloud user ID>/
 *   driver_webdav_username / _password   the CardDAV account's
 *
 * Kolab's calendar gets the same login (CalDAV driver, dav_connect hook)
 * and the same server (calendar_caldav_server).
 *
 * No setting and no second password is stored, and Roundav's own settings
 * are locked (dont_override): nothing unencrypted, no fallback to the mail
 * password. Per session, the Roundcube session holds what Nextcloud said
 * (its user ID from current-user-principal, which need not equal the login
 * name; folder counts, Talk, the default calendar) and the encrypted
 * Nextcloud cookies.
 *
 * This plugin owns these settings, whatever etc/ sets: driver_webdav_*,
 * driver_webdav_auth_type and _keep_session, roundav_folder_count_property
 * and roundav_tree_depth 1 (only where Nextcloud reports folder counts),
 * kolab_dav_default_folder_regex, calendar_driver (caldav) and
 * calendar_caldav_server.
 *
 * Without a Nextcloud CardDAV account Roundav stays unconfigured, the
 * Calendar button is hidden, and opening the calendar leads to the Contacts
 * (CardDAV) settings with a note on how to connect Nextcloud; the calendar's
 * own background requests then fail against an address nothing listens on
 * (calendar_caldav_server below), nothing else.
 *
 * Loaded before roundav and calendar (the release defaults put them in that
 * order): they read some settings when they start.
 */
use MStilkerich\RCMCardDAV\Frontend\Utils;

class mailstack_cloudfiles extends rcube_plugin
{
    public $task = '?(?!login|logout).*';

    private const KEYS = ['driver_webdav_url', 'driver_webdav_prefix',
                          'driver_webdav_username', 'driver_webdav_password'];
    private const SESSION = 'mailstack_cloudfiles_uid';
    private const JAR = 'mailstack_cloudfiles_dav_cookies';
    /** Nextcloud's number of subfolders of a folder (WebDAV property). */
    private const FOLDER_COUNT = '{http://nextcloud.org/ns}contained-folder-count';
    /** RFC 6638: the calendar new invitations go to (on the scheduling inbox). */
    private const DEFAULT_CALENDAR = '{urn:ietf:params:xml:ns:caldav}schedule-default-calendar-URL';

    /** Computed once per request: the four values, or all null. */
    private $values = null;

    /** This request's Nextcloud cookie jar (key => jar), stored on shutdown. */
    private static $jars = [];
    private static $sealing = false;

    public function init()
    {
        $this->add_texts('localization/');
        // Answer whenever anyone reads these settings from now on.
        $this->add_hook('config_get', [$this, 'config_get']);
        $this->add_hook('startup', [$this, 'startup']);
        // Kolab's calendar (CalDAV driver) sends every request through this
        // hook: give it the CardDAV account's login, never the mail login.
        $this->add_hook('dav_connect', [$this, 'dav_connect']);
    }

    public function config_get($args)
    {
        if (in_array($args['name'], self::KEYS, true)) {
            $args['result'] = $this->values()[$args['name']];
        } elseif ($args['name'] === 'driver_webdav_auth_type') {
            // Roundav (3.2.0+): send the login with the first request. Sabre's
            // default (Basic or Digest) sends every request twice, first
            // without login, to learn the method.
            if (!empty($this->values()['driver_webdav_url'])) {
                $args['result'] = \Sabre\DAV\Client::AUTH_BASIC;
            }
        } elseif ($args['name'] === 'driver_webdav_keep_session') {
            // Roundav (3.2.0+) keeps Nextcloud's session cookies in the
            // Roundcube session: a login without a session costs ~0.5 s at
            // Nextcloud, a request in one ~0.1 s (measured 2026-10-07); a
            // folder tree of n folders takes n+1 requests. Roundav keeps its
            // own cookies, so it logs in once beside the shared jar below.
            if (!empty($this->values()['driver_webdav_url'])) {
                $args['result'] = true;
            }
        } elseif ($args['name'] === 'roundav_tree_depth') {
            // One folder level per request where Nextcloud reports subfolder
            // counts (checked once per session); otherwise as configured.
            if (!empty($this->values()['folder_counts'])) {
                $args['result'] = 1;
            }
        } elseif ($args['name'] === 'roundav_folder_count_property') {
            // Exact expand arrows (our Roundav patch): asked only from a server
            // that reported the counts (checked once per session).
            if (!empty($this->values()['folder_counts'])) {
                $args['result'] = self::FOLDER_COUNT;
            }
        } elseif ($args['name'] === 'kolab_dav_default_folder_regex') {
            // Kolab's calendar marks the folder whose href matches as the
            // default: preselected for invitations and new events (unless the
            // user chose one in the calendar settings). Nextcloud's own
            // default calendar, as it reports it; else Kolab's default rule.
            $path = $this->values()['default_calendar'];
            if ($path !== null) {
                $args['result'] = '~^(https?://[^/]+)?' . preg_quote(rtrim($path, '/'), '~') . '/?$~';
            }
        } elseif ($args['name'] === 'calendar_driver') {
            $args['result'] = 'caldav';
        } elseif ($args['name'] === 'calendar_caldav_server') {
            $v = $this->values();
            // Without a Nextcloud account: an address nothing listens on.
            $args['result'] = $v['driver_webdav_url']
                ? $v['driver_webdav_url'] . ltrim($v['caldav_path'], '/')
                : 'http://127.0.0.1:9';
        } elseif ($args['name'] === 'dont_override') {
            // Roundav's settings page shows nothing to edit, saves nothing.
            $args['result'] = array_values(array_unique(array_merge((array) $args['result'], self::KEYS)));
        }
        return $args;
    }

    public function dav_connect($args)
    {
        $request = $args['request'];
        $v = $this->values();
        if ($v['driver_webdav_url'] && self::same_origin((string) $request->getUrl(), $v['driver_webdav_url'])) {
            $request->setAuth($v['driver_webdav_username'], $v['driver_webdav_password']);
            // Reuse Nextcloud's session across requests, as Nextcloud
            // recommends for DAV clients: a fresh Basic-auth login costs
            // ~450 ms (password hashing first, then the app password), a
            // request in an existing session ~70 ms (measured 2026-10-06).
            // The jar lives in this Roundcube session and ends with it.
            $request->setCookieJar(self::jar($v['driver_webdav_url'], $v['driver_webdav_username']));
        } else {
            $request->setAuth('');   // drop the mail login the client put in
        }
        return $args;
    }

    /**
     * The Nextcloud session (its cookies) for one account, kept in this
     * Roundcube session and shared by the identity check and the calendar:
     * whichever talks to Nextcloud first logs in, the other reuses it
     * (Roundav keeps its own, driver_webdav_keep_session). Per account: a
     * session never carries over to another login.
     *
     * In the session table the jar is encrypted with Roundcube's des_key, as
     * Roundcube keeps the IMAP password there: a copy of the database alone
     * holds no usable Nextcloud session.
     */
    private static function jar($origin, $username)
    {
        $key = md5($origin . '|' . $username);
        if (!isset(self::$jars[$key])) {
            // true: keep session cookies (Nextcloud's have no expiry) when stored.
            $jar = new HTTP_Request2_CookieJar(true, false);
            $sealed = $_SESSION[self::JAR][$key] ?? null;
            $plain = is_string($sealed) ? rcube::get_instance()->decrypt($sealed) : false;
            $data = is_string($plain) ? @unserialize($plain, ['allowed_classes' => false]) : false;
            if (is_array($data) && isset($data['cookies'], $data['serializeSession'], $data['useList'])) {
                $jar->__unserialize($data);
            }
            self::$jars = [$key => $jar];      // one account at a time
            if (!self::$sealing) {
                self::$sealing = true;
                // Runs before Roundcube writes the session (rcube::shutdown).
                rcube::get_instance()->add_shutdown_function([self::class, 'seal']);
            }
        }
        return self::$jars[$key];
    }

    /** Stores this request's jar in the session, encrypted. */
    public static function seal()
    {
        $sealed = [];
        foreach (self::$jars as $key => $jar) {
            $cipher = rcube::get_instance()->encrypt(serialize($jar->__serialize()));
            if (is_string($cipher)) {
                $sealed[$key] = $cipher;
            }
        }
        $_SESSION[self::JAR] = $sealed;
    }

    /** Credentials and session cookies are scoped to the full HTTP origin. */
    private static function same_origin($url, $origin)
    {
        $a = parse_url($url);
        $b = parse_url($origin);
        if (!$a || !$b || empty($a['host']) || empty($b['host'])
            || empty($a['scheme']) || empty($b['scheme'])) {
            return false;
        }
        $scheme = strtolower($a['scheme']);
        if (!in_array($scheme, ['http', 'https'], true) || $scheme !== strtolower($b['scheme'])) {
            return false;
        }
        $default = $scheme === 'https' ? 443 : 80;
        return strtolower($a['host']) === strtolower($b['host'])
            && ($a['port'] ?? $default) === ($b['port'] ?? $default);
    }

    /** A Sabre client that sends and keeps the account's Nextcloud cookies. */
    private static function with_session(\Sabre\DAV\Client $client, $origin, $username)
    {
        $jar = self::jar($origin, $username);

        $client->on('beforeRequest', function ($request) use ($jar, $origin) {
            $url = $request->getUrl();
            if (self::same_origin($url, $origin) && ($cookies = $jar->getMatching(new Net_URL2($url), true))) {
                $request->setHeader('Cookie', $cookies);
            }
        });
        $client->on('afterRequest', function ($request, $response) use ($jar, $origin) {
            $url = $request->getUrl();
            $headers = $response->getHeaderAsArray('Set-Cookie');
            if (!$headers || !self::same_origin($url, $origin)) {
                return;
            }
            // Parsed by HTTP_Request2 itself (expiry, path, domain).
            $parsed = new HTTP_Request2_Response('HTTP/1.1 ' . $response->getStatus() . ' X', false, $url);
            foreach ($headers as $header) {
                $parsed->parseHeaderLine('Set-Cookie: ' . $header);
            }
            $parsed->parseHeaderLine('');
            $jar->addCookiesFromResponse($parsed, new Net_URL2($url));
        });
        return $client;
    }

    public function startup($args)
    {
        $rc = rcmail::get_instance();
        if ($rc->task == 'settings') {
            // Registered now, after roundav's own hook: hide its empty page.
            $this->add_hook('preferences_sections_list', [$this, 'hide_section']);
            if ($rc->action == 'plugin.carddav' && rcube_utils::get_input_string('_nocloud', rcube_utils::INPUT_GET)) {
                $rc->output->show_message('mailstack_cloudfiles.nocloud', 'notice', null, true, 30);
            }
        }
        // Full pages carry the task bar; framed ones (message preview) too
        // may carry Roundav's buttons. Not AJAX.
        $html = $rc->output->type == 'html';
        $page = $html && !$rc->output->framed && empty($_REQUEST['_framed']);
        if ($html && empty($this->values()['driver_webdav_url'])) {
            if ($page && $rc->task == 'calendar') {
                $rc->output->redirect(['_task' => 'settings', '_action' => 'plugin.carddav', '_nocloud' => 1]);
            }
            // No Nextcloud: no Calendar, and none of Roundav's cloud buttons
            // (they would only fail): "From cloud" in the composer, "Save
            // all" in the message header, "Save to cloud" in the attachment
            // menu and on the attachment page.
            $rc->output->add_header(html::tag('style', [],
                '#taskmenu a.button-calendar, #compose-attachments button.attach.cloud,'
                . ' #message-header a.filesaveall, #attachmenusaveas, li:has(> #attachmenusaveas),'
                . ' #saveas { display: none !important; }'));
        } elseif ($page) {
            $this->nextcloud_buttons();
        }
        return $args;
    }

    /**
     * Files and Talk in the task bar right after Calendar: links into the
     * user's Nextcloud, opened in a new tab; Talk only where that Nextcloud
     * has it (its capabilities). Appended when the task bar is rendered, so
     * they follow the buttons other plugins (Calendar) added.
     */
    private function nextcloud_buttons()
    {
        $v = $this->values();
        $base = rtrim($v['driver_webdav_url'], '/') . $v['nextcloud_path'];
        $buttons = ['files' => ['apps/files/', '\\f07c']];
        if ($v['talk']) {
            $buttons['talk'] = ['apps/spreed/', '\\f086'];
        }
        $css = '';
        foreach ($buttons as $name => [, $icon]) {
            $css .= '#taskmenu a.button-nc-' . $name . ':before { content: "' . $icon . '"; } ';
        }
        $rc = rcmail::get_instance();
        $rc->output->add_header(html::tag('style', [], $css));
        $this->add_hook('template_container', function ($args) use ($buttons, $base, $rc) {
            if (($args['name'] ?? '') === 'taskbar') {
                foreach ($buttons as $name => [$app]) {
                    $args['content'] = ($args['content'] ?? '') . $rc->output->button([
                        'href'       => $base . $app,
                        'target'     => '_blank',
                        'rel'        => 'noopener',
                        'class'      => 'button-nc-' . $name,
                        'innerclass' => 'button-inner',
                        'label'      => 'mailstack_cloudfiles.' . $name,
                        'type'       => 'link',
                    ]);
                }
            }
            return $args;
        });
    }

    private function values()
    {
        if ($this->values !== null) {
            return $this->values;
        }
        $this->values = array_fill_keys(self::KEYS, null) + ['caldav_path' => null, 'folder_counts' => false,
            'nextcloud_path' => null, 'talk' => false, 'default_calendar' => null];   // never a stored value
        $rc = rcmail::get_instance();
        if (empty($rc->user->ID)) {
            return $this->values;
        }
        $account = $this->nextcloud_account($rc);
        if ($account) {
            $this->values = [
                'driver_webdav_url'      => $account['origin'],
                'driver_webdav_prefix'   => $account['path'] . 'remote.php/dav/files/' . rawurlencode($account['uid']) . '/',
                'driver_webdav_username' => $account['username'],
                'driver_webdav_password' => $account['password'],
                'caldav_path'            => $account['path'] . 'remote.php/dav',
                'folder_counts'          => $account['folder_counts'],
                'nextcloud_path'         => $account['path'],
                'talk'                   => $account['talk'],
                'default_calendar'       => $account['default_calendar'],
            ];
        }
        return $this->values;
    }

    /** To the container log (Roundcube's own log goes to a file here). */
    private static function log($text)
    {
        error_log('mailstack_cloudfiles: ' . $text);
    }

    public function hide_section($args)
    {
        unset($args['list']['roundav']);
        return $args;
    }

    /**
     * The user's first CardDAV account whose server is a Nextcloud, with the
     * Nextcloud user ID. Whether it is one is asked from the server (the
     * discovery URL may be just "https://host"), not guessed from the URL.
     */
    private function nextcloud_account($rc)
    {
        $db = $rc->get_dbh();
        $res = $db->query(
            'SELECT id, username, password, discovery_url FROM ' . $db->table_name('carddav_accounts', true)
            . ' WHERE user_id = ? ORDER BY id', $rc->user->ID);
        while ($res && ($row = $db->fetch_assoc($res))) {
            $url = Utils::replacePlaceholdersUrl((string) $row['discovery_url']);
            // RCMCardDAV accepts a bare host as discovery URL.
            if (!preg_match('#^https?://#i', $url)) {
                $url = 'https://' . $url;
            }
            $p = parse_url($url);
            if (empty($p['host'])) {
                continue;
            }
            // Nextcloud's root: everything before /remote.php/, else the URL's path.
            $path = $p['path'] ?? '/';
            $cut = strpos($path, '/remote.php/');
            $path = rtrim($cut === false ? $path : substr($path, 0, $cut), '/') . '/';
            $origin = strtolower($p['scheme']) . '://' . $p['host'] . (isset($p['port']) ? ':' . $p['port'] : '') . '/';
            // RCMCardDAV's placeholders (%u, %p, ...), as RCMCardDAV itself
            // resolves them for an admin preset.
            $password = Utils::replacePlaceholdersPassword(Utils::decryptPassword((string) $row['password']));
            $username = Utils::replacePlaceholdersUsername((string) $row['username']);
            if ($password === '' || $password === '0' || $username === '') {
                continue;
            }
            $account = ['id' => $row['id'], 'origin' => $origin, 'path' => $path,
                        'username' => $username, 'password' => $password];
            $uid = $this->user_id($account);
            if ($uid !== null) {
                $account['uid'] = $uid;
                $key = self::cache_key($account);
                $account['folder_counts'] = !empty($_SESSION[self::SESSION . '_counts'][$key]);
                $account['talk'] = !empty($_SESSION[self::SESSION . '_talk'][$key]);
                $account['default_calendar'] = $_SESSION[self::SESSION . '_defcal'][$key] ?? null;
                return $account;
            }
        }
        return null;
    }

    /** One account's key in the session caches. */
    private static function cache_key($account)
    {
        return $account['id'] . '|' . $account['origin'] . $account['path'] . '|' . $account['username'];
    }

    /**
     * Nextcloud's user ID for these credentials, or null if the server is not
     * a Nextcloud (or refuses them). Cached for the session, the "no" too --
     * but not a server that could not be reached, nor an unexpected error:
     * asked again a minute later.
     */
    private function user_id($account)
    {
        $cache_key = self::cache_key($account);
        if (isset($_SESSION[self::SESSION]) && array_key_exists($cache_key, $_SESSION[self::SESSION])) {
            return $_SESSION[self::SESSION][$cache_key];
        }
        if (($_SESSION[self::SESSION . '_retry'][$cache_key] ?? 0) > time()) {
            return null;
        }
        unset($_SESSION[self::SESSION . '_retry'][$cache_key]);
        $_SESSION[self::SESSION][$cache_key] = null;
        try {
            // In the account's Nextcloud session: this check is the first
            // request of a Roundcube session, so it logs in for the others.
            $client = self::with_session(new \Sabre\DAV\Client(['baseUri' => $account['origin'],
                'userName' => $account['username'], 'password' => $account['password'],
                'authType' => \Sabre\DAV\Client::AUTH_BASIC]), $account['origin'], $account['username']);
            $client->addCurlSetting(CURLOPT_CONNECTTIMEOUT, 3);
            $client->addCurlSetting(CURLOPT_TIMEOUT, 10);
            $props = $client->propFind($account['path'] . 'remote.php/dav/', ['{DAV:}current-user-principal'], 0);
            $principal = $props['{DAV:}current-user-principal'] ?? null;
            $href = is_array($principal) ? ($principal[0]['value'] ?? null) : null;
            if (is_object($principal) && method_exists($principal, 'getHref')) {
                $href = $principal->getHref();
            }
            if (!is_string($href) || !preg_match('#/principals/users/([^/]+)/?$#', $href, $m)) {
                self::log('no Nextcloud user principal at ' . $account['origin'] . $account['path'] . 'remote.php/dav/ (got '
                          . get_debug_type($principal) . ')');
                return null;
            }
            $uid = rawurldecode($m[1]);
            // The gate for Roundav's one-level folder tree: does this server
            // report how many folders each folder contains? Asked once per
            // session, with the identity, from the server itself rather than
            // inferred from a version number.
            $files = $account['path'] . 'remote.php/dav/files/' . rawurlencode($uid) . '/';
            $count = self::FOLDER_COUNT;
            try {
                $found = $client->propFind($files, [$count], 0);
                $counts = isset($found[$count]) && is_numeric($found[$count]);
            } catch (Throwable $e) {
                self::log('folder counts, account ' . $account['id'] . ': ' . get_class($e));
                $counts = false;
            }
            $_SESSION[self::SESSION . '_counts'][$cache_key] = $counts;
            $_SESSION[self::SESSION . '_defcal'][$cache_key] = self::default_calendar($client, $account, $uid);
            $_SESSION[self::SESSION . '_talk'][$cache_key] = self::has_talk($client, $account);
            return $_SESSION[self::SESSION][$cache_key] = $uid;
        } catch (\Sabre\HTTP\ClientException $e) {
            // Not reached (network, TLS): no verdict, wait before trying again.
            unset($_SESSION[self::SESSION][$cache_key]);
            $_SESSION[self::SESSION . '_retry'][$cache_key] = time() + 60;
            self::log('Nextcloud identity check, account ' . $account['id'] . ': not reached (' . get_class($e) . ')');
            return null;
        } catch (\Sabre\HTTP\ClientHttpException $e) {
            $status = $e->getHttpStatus();
            if (($status >= 500 && $status <= 599) || $status == 408 || $status == 429) {
                unset($_SESSION[self::SESSION][$cache_key]);
                $_SESSION[self::SESSION . '_retry'][$cache_key] = time() + 60;
            }
            // 401/403/404 (and other non-5xx answers except 408/429) keep the
            // session's "no"; 408 and 429 (Nextcloud's throttling) are retried.
            self::log('Nextcloud identity check, account ' . $account['id'] . ': HTTP ' . $status);
            return null;
        } catch (Throwable $e) {
            // Not a verdict about the server (a bug here or in a library):
            // no "no" for the session, asked again later.
            unset($_SESSION[self::SESSION][$cache_key]);
            $_SESSION[self::SESSION . '_retry'][$cache_key] = time() + 60;
            self::log('Nextcloud identity check, account ' . $account['id'] . ': ' . get_class($e) . ': ' . $e->getMessage());
            return null;
        }
    }

    /**
     * The path of the calendar Nextcloud puts new invitations in (its
     * default calendar, user-settable there), from the scheduling inbox; null
     * when the server does not say. Asked once per session, with the identity.
     */
    private static function default_calendar($client, $account, $uid)
    {
        try {
            $inbox = $account['path'] . 'remote.php/dav/calendars/' . rawurlencode($uid) . '/inbox/';
            $found = $client->propFind($inbox, [self::DEFAULT_CALENDAR], 0);
            $href = $found[self::DEFAULT_CALENDAR] ?? null;
            if (is_array($href)) {   // Sabre's {DAV:}href list
                $href = $href[0]['value'] ?? null;
            } elseif (is_object($href) && method_exists($href, 'getHref')) {
                $href = $href->getHref();
            }
            $path = is_string($href) ? (string) parse_url($href, PHP_URL_PATH) : '';
            return strpos($path, $account['path'] . 'remote.php/dav/calendars/') === 0 ? $path : null;
        } catch (Throwable $e) {
            self::log('default calendar, account ' . $account['id'] . ': ' . get_class($e));
            return null;
        }
    }

    /** Whether the Nextcloud has Talk (spreed) enabled, from its capabilities. */
    private static function has_talk($client, $account)
    {
        try {
            $r = $client->request('GET', $account['path'] . 'ocs/v2.php/cloud/capabilities?format=json',
                null, ['OCS-APIRequest' => 'true', 'Accept' => 'application/json']);
            $caps = json_decode((string) ($r['body'] ?? ''), true)['ocs']['data']['capabilities'] ?? null;
            return ($r['statusCode'] ?? 0) == 200 && is_array($caps) && isset($caps['spreed']);
        } catch (Throwable $e) {
            self::log('Talk check, account ' . $account['id'] . ': ' . get_class($e));
            return false;
        }
    }
}

