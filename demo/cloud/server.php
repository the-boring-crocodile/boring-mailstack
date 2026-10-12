<?php
// Pond Cloud: the demo's stand-in for a Nextcloud (DEMO ONLY).
//
// Serves the four characters' calendars, addressbooks and files under the
// same paths as a Nextcloud, so Roundcube's Contacts, Calendar and cloud
// files work in the demo exactly as against a real one:
//
//   /remote.php/dav/principals/users/<user>/
//   /remote.php/dav/calendars/<user>/<calendar>/
//   /remote.php/dav/addressbooks/users/<user>/<addressbook>/
//   /remote.php/dav/files/<user>/
//
// Plain HTTP on the internal demo network only, Basic auth with the demo
// passwords (users.json, written by tools/demo). Built on sabre/dav from
// the Roundcube image (Roundav brings it), run by PHP's built-in server.
// The data (seed.php) lives in the container and is seeded on every start.

use Sabre\DAV;
use Sabre\DAVACL;
use Sabre\CalDAV;
use Sabre\CardDAV;

require '/usr/src/roundcubemail/vendor/autoload.php';

const DATA = '/var/pond-cloud';

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
if (strpos($path, '/remote.php/dav') !== 0) {
    if ($path === '/status.php') {   // what Nextcloud answers, roughly
        header('Content-Type: application/json');
        echo json_encode(['installed' => true, 'productname' => 'Pond Cloud (demo)']);
        return true;
    }
    if ($path === '/ocs/v2.php/cloud/capabilities') {   // as a Nextcloud with Talk (spreed)
        header('Content-Type: application/json');
        echo json_encode(['ocs' => ['meta' => ['status' => 'ok', 'statuscode' => 200],
            'data' => ['capabilities' => ['spreed' => ['features' => ['chat-v2']]]]]]);
        return true;
    }
    http_response_code(404);
    echo "Pond Cloud (demo): only /remote.php/dav/ here.\n";
    return true;
}

// A session cookie, as Nextcloud sets one: clients that keep it skip the
// expensive login there. Pond Cloud only notes whether it came back.
$session = isset($_COOKIE['pondcloud_session']) ? 'session' : 'no session';
if (!isset($_COOKIE['pondcloud_session'])) {
    header('Set-Cookie: pondcloud_session=' . bin2hex(random_bytes(8)) . '; Path=/; HttpOnly');
}

// One line per request in the container log: method, path, status, user.
register_shutdown_function(function () use ($path, $session) {
    error_log(sprintf('%s %s -> %d (%s, %s)', $_SERVER['REQUEST_METHOD'] ?? '?', $path,
        http_response_code(), $_SERVER['PHP_AUTH_USER'] ?? '-', $session));
});

$users = json_decode(file_get_contents('/run/demo/users.json'), true);
$pdo = new PDO('sqlite:' . DATA . '/dav.sqlite');
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$pdo->exec('PRAGMA busy_timeout = 5000');

$principals = new DAVACL\PrincipalBackend\PDO($pdo);

// Nextcloud keeps addressbooks one level deeper (addressbooks/users/<u>).
class PondAddressBookRoot extends CardDAV\AddressBookRoot
{
    public function getName()
    {
        return 'users';
    }
}

// Homes as Nextcloud has them: principals/users/<u> keeps its calendars
// in calendars/<u> and its addressbooks in addressbooks/users/<u>.
// (sabre/dav's defaults assume principals/<u>.)
class PondCalDAV extends CalDAV\Plugin
{
    public function getCalendarHomeForPrincipal($principalUrl)
    {
        return preg_match('#^principals/users/([^/]+)$#', $principalUrl, $m) ? 'calendars/' . $m[1] : null;
    }
}

class PondCardDAV extends CardDAV\Plugin
{
    protected function getAddressbookHomeForPrincipal($principal)
    {
        return preg_match('#^principals/users/([^/]+)$#', $principal, $m) ? 'addressbooks/users/' . $m[1] : null;
    }
}

// Files: only the logged-in user's own folder exists for them.
class PondFiles extends DAV\Collection
{
    public function __construct(private string $user)
    {
    }

    public function getName()
    {
        return 'files';
    }

    public function getChildren()
    {
        return [new class(DATA . '/files/' . $this->user, $this->user) extends DAV\FS\Directory {
            public function __construct($path, private string $user)
            {
                parent::__construct($path);
            }

            public function getName()
            {
                return $this->user;
            }
        }];
    }
}

// Basic auth against users.json; principals live where Nextcloud has them.
$valid = fn($username, $password) => isset($users[$username]) && hash_equals($users[$username], (string) $password);

class PondAuth extends DAV\Auth\Backend\AbstractBasic
{
    protected $principalPrefix = 'principals/users/';
    protected $realm = 'Pond Cloud';

    public function __construct(private Closure $valid)
    {
    }

    protected function validateUserPass($username, $password)
    {
        return ($this->valid)($username, $password);
    }
}
$authBackend = new PondAuth($valid);

// The user is known only after authentication; files need it up front.
$who = $_SERVER['PHP_AUTH_USER'] ?? null;
if ($who !== null && !$valid($who, $_SERVER['PHP_AUTH_PW'] ?? '')) {
    $who = null;
}

if ($who === null) {
    // Everything here needs a login, as at Nextcloud; answer before any
    // node is looked up (otherwise a user's files folder is a 404).
    http_response_code(401);
    header('WWW-Authenticate: Basic realm="Pond Cloud", charset="UTF-8"');
    return true;
}

$tree = [
    new DAV\SimpleCollection('principals', [new DAVACL\PrincipalCollection($principals, 'principals/users')]),
    new CalDAV\CalendarRoot($principals, new CalDAV\Backend\PDO($pdo), 'principals/users'),
    new DAV\SimpleCollection('addressbooks', [new PondAddressBookRoot($principals, new CardDAV\Backend\PDO($pdo), 'principals/users')]),
    new PondFiles($who),
];

$server = new DAV\Server($tree);
$server->setBaseUri('/remote.php/dav/');
$server->addPlugin(new DAV\Auth\Plugin($authBackend));
$acl = new DAVACL\Plugin();
$acl->hideNodesFromListings = true;
$acl->principalCollectionSet = ['principals/users'];
// Plain files carry no ACL of their own; PondFiles already scopes them.
$acl->setDefaultAcl([['principal' => '{DAV:}authenticated', 'privilege' => '{DAV:}all', 'protected' => true]]);
$server->addPlugin($acl);
$server->addPlugin(new PondCalDAV());
$server->addPlugin(new PondCardDAV());
$server->addPlugin(new DAV\Sync\Plugin());
$server->addPlugin(new DAV\Locks\Plugin(new DAV\Locks\Backend\File(DATA . '/locks.dat')));
// Nextcloud reports how many folders a folder contains (file trees use it to
// show expand arrows only where there is something to expand).
$server->on('propFind', function (DAV\PropFind $propFind, DAV\INode $node) {
    if ($node instanceof DAV\FS\Directory) {
        $propFind->handle('{http://nextcloud.org/ns}contained-folder-count', function () use ($node) {
            return count(array_filter($node->getChildren(), fn ($child) => $child instanceof DAV\ICollection));
        });
    }
});

// Nextcloud's default calendar for invitations (RFC 6638, on the scheduling
// inbox): "personal", as Nextcloud's own default; the demo seeds a second
// calendar after it, so a client that ignores this picks the other one.
$server->on('propFind', function (DAV\PropFind $propFind, DAV\INode $node) {
    if ($node instanceof CalDAV\Schedule\IInbox) {
        $propFind->handle('{urn:ietf:params:xml:ns:caldav}schedule-default-calendar-URL', function () use ($node) {
            $user = basename($node->getOwner());
            return new DAV\Xml\Property\Href('/remote.php/dav/calendars/' . rawurlencode($user) . '/personal/');
        });
    }
});

// Compact XML, as Nextcloud sends it: some clients (Kolab's) take the first
// child of a property for its <href>, and indentation would come first.
$server->on('afterMethod:*', function ($request, $response) {
    if ($response->getStatus() == 207 && is_string($body = $response->getBodyAsString())) {
        $response->setBody(preg_replace('/>\s+</', '><', $body));
    }
});
$server->exec();
return true;
