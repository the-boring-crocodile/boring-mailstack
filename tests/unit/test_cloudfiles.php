<?php
// Isolated plugin regressions; run with PHP + curl, no network or Roundcube.
namespace Sabre\HTTP {
    class ClientException extends \Exception {}
    class ClientHttpException extends \Exception {
        public function getHttpStatus() { return $this->getCode(); }
    }
}
namespace Sabre\DAV {
    class Client {
        const AUTH_BASIC = 1;
        public static $failure;
        public static $calls = 0;
        public static $last;
        public $options = [];
        public $events = [];
        public function __construct($settings) { self::$last = $this; }
        public function addCurlSetting($key, $value) { $this->options[$key] = $value; }
        public function on($name, $callback) { $this->events[$name] = $callback; }
        public function propFind($path, $props, $depth) {
            self::$calls++;
            if (self::$failure) { throw self::$failure; }
            return ['{DAV:}current-user-principal' => [['value' => '/principals/users/person/']]];
        }
        public function request(...$args) { return []; }
    }
}
namespace MStilkerich\RCMCardDAV\Frontend {
    class Utils {
        public static function replacePlaceholdersUrl($v) { return $v; }
        public static function decryptPassword($v) { return $v; }
        public static function replacePlaceholdersPassword($v) { return $v; }
        public static function replacePlaceholdersUsername($v) { return $v; }
    }
}
namespace {
    class rcube_plugin {}
    class Net_URL2 { public function __construct($url) {} }
    class HTTP_Request2_CookieJar {
        public $cookies = [];
        public function __construct(...$args) {}
        public function getMatching(...$args) { return 'session=synthetic'; }
        public function __serialize() { return ['cookies' => $this->cookies, 'serializeSession' => true, 'useList' => false]; }
        public function __unserialize(array $data) { $this->cookies = $data['cookies']; }
    }
    class rcube {
        public static $shutdown = [];
        public static function get_instance() { return new self(); }
        public function add_shutdown_function($f) { self::$shutdown[] = $f; }
        // Stand-in for des_key encryption: reversible, not plain text.
        public function encrypt($clear) { return 'X' . base64_encode(strrev($clear)); }
        public function decrypt($cipher) { return $cipher[0] === 'X' ? strrev(base64_decode(substr($cipher, 1))) : false; }
    }
    class TestRequest {
        public $auth = [];
        public $headers = [];
        public $jar;
        public function __construct(public $url) {}
        public function getUrl() { return $this->url; }
        public function setAuth(...$args) { $this->auth = $args; }
        public function setCookieJar($jar) { $this->jar = $jar; }
        public function setHeader($key, $value) { $this->headers[$key] = $value; }
    }
    function check($condition, $label) {
        if (!$condition) { throw new \RuntimeException($label); }
    }
    require __DIR__ . '/../../roundcube/plugins/mailstack_cloudfiles/mailstack_cloudfiles.php';
    $plugin = new mailstack_cloudfiles();
    $uid = new ReflectionMethod($plugin, 'user_id');
    $keyMethod = new ReflectionMethod($plugin, 'cache_key');
    $origin = new ReflectionMethod($plugin, 'same_origin');
    $account = ['id' => 1, 'origin' => 'https://cloud.test/', 'path' => '/',
                'username' => 'person', 'password' => 'synthetic'];
    $key = $keyMethod->invoke(null, $account);
    foreach ([new \Sabre\HTTP\ClientException('unavailable'),
              new \Sabre\HTTP\ClientHttpException('unavailable', 503),
              new \Sabre\HTTP\ClientHttpException('throttled', 429),
              new \Sabre\HTTP\ClientHttpException('timeout', 408)] as $failure) {
        $_SESSION = [];
        \Sabre\DAV\Client::$failure = $failure;
        $before = \Sabre\DAV\Client::$calls;
        check($uid->invoke($plugin, $account) === null, 'transient returns null');
        check(!array_key_exists($key, $_SESSION['mailstack_cloudfiles_uid']), 'no negative verdict');
        check($_SESSION['mailstack_cloudfiles_uid_retry'][$key] >= time() + 59, 'retry deadline');
        $uid->invoke($plugin, $account);
        check(\Sabre\DAV\Client::$calls === $before + 1, 'retry suppressed');
        $_SESSION['mailstack_cloudfiles_uid_retry'][$key] = time() - 1;
        \Sabre\DAV\Client::$failure = null;
        check($uid->invoke($plugin, $account) === 'person', 'recovers after deadline');
        check(\Sabre\DAV\Client::$last->options[CURLOPT_CONNECTTIMEOUT] === 3, 'connect timeout');
        check(\Sabre\DAV\Client::$last->options[CURLOPT_TIMEOUT] === 10, 'total timeout');
    }
    foreach ([401, 403, 404] as $status) {
        $_SESSION = [];
        \Sabre\DAV\Client::$failure = new \Sabre\HTTP\ClientHttpException('refused', $status);
        $before = \Sabre\DAV\Client::$calls;
        $uid->invoke($plugin, $account);
        $uid->invoke($plugin, $account);
        check(\Sabre\DAV\Client::$calls === $before + 1, 'negative verdict retained');
        check(array_key_exists($key, $_SESSION['mailstack_cloudfiles_uid']), 'negative cached');
    }
    check($origin->invoke(null, 'https://CLOUD.test:443/path', 'https://cloud.test/'), 'effective default port');
    foreach (['http://cloud.test/', 'https://cloud.test:8443/', 'https://other.test/', '/relative'] as $url) {
        check(!$origin->invoke(null, $url, 'https://cloud.test/'), 'foreign origin rejected');
    }
    $values = new ReflectionProperty($plugin, 'values');
    $values->setValue($plugin, ['driver_webdav_url' => 'https://cloud.test/',
                              'driver_webdav_username' => 'person', 'driver_webdav_password' => 'synthetic']);
    foreach (['https://cloud.test:443/path' => true, 'http://cloud.test/' => false,
              'https://cloud.test:8443/' => false] as $url => $same) {
        $request = new TestRequest($url);
        $plugin->dav_connect(['request' => $request]);
        check($same ? count($request->auth) === 2 : $request->auth === [''], 'auth origin gate');
        check($same === ($request->jar !== null), 'cookie jar origin gate');
        $client = new \Sabre\DAV\Client([]);
        $with = new ReflectionMethod($plugin, 'with_session');
        $with->invoke(null, $client, 'https://cloud.test/', 'person');
        ($client->events['beforeRequest'])($request);
        check($same === isset($request->headers['Cookie']), 'cookie header origin gate');
    }
    // The cookie jar goes into the session encrypted, once per request, and
    // comes back from it in the next request.
    check(count(rcube::$shutdown) === 1, 'jar sealed on shutdown, registered once');
    $jarMethod = new ReflectionMethod($plugin, 'jar');
    $jarMethod->invoke(null, 'https://cloud.test/', 'person')->cookies = [['name' => 'nc_session', 'value' => 'cookie-secret']];
    call_user_func(rcube::$shutdown[0]);
    $stored = $_SESSION['mailstack_cloudfiles_dav_cookies'];
    check(count($stored) === 1 && is_string(reset($stored)), 'one jar stored as a string');
    check(strpos(serialize($_SESSION), 'cookie-secret') === false, 'no cookie in the clear in the session');
    (new ReflectionProperty($plugin, 'jars'))->setValue(null, []);
    $back = $jarMethod->invoke(null, 'https://cloud.test/', 'person');
    check(($back->cookies[0]['value'] ?? null) === 'cookie-secret', 'jar restored in the next request');
    $_SESSION['mailstack_cloudfiles_dav_cookies'] = [key($stored) => 'garbage'];
    (new ReflectionProperty($plugin, 'jars'))->setValue(null, []);
    check($jarMethod->invoke(null, 'https://cloud.test/', 'person')->cookies === [], 'undecryptable jar: a fresh one');

    $db = new class {
        public $rows;
        public function query(...$args) { return true; }
        public function table_name(...$args) { return 'carddav_accounts'; }
        public function fetch_assoc($res) { return array_shift($this->rows); }
    };
    $rc = new class($db) {
        public function __construct(public $db) { $this->user = (object) ['ID' => 1]; }
        public function get_dbh() { return $this->db; }
    };
    $lookup = new ReflectionMethod($plugin, 'nextcloud_account');
    foreach (['', '0'] as $password) {
        $db->rows = [['id' => 1, 'discovery_url' => 'https://cloud.test/', 'username' => 'person', 'password' => $password]];
        $before = \Sabre\DAV\Client::$calls;
        check($lookup->invoke($plugin, $rc) === null, 'falsy password skipped');
        check(\Sabre\DAV\Client::$calls === $before, 'no request for falsy password');
    }
    echo "PASS cloudfiles timeouts, retry, verdicts, origin gates, falsy passwords, encrypted cookie jar\n";
}
