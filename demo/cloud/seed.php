<?php
// Pond Cloud (DEMO ONLY): create the store and give each character a
// calendar with a few routine appointments, an addressbook with their
// colleagues and a little folder of files. Runs on every start; seeds only
// what is missing, so appointments the demo user adds stay.
//
// Nothing here belongs to the plot (demo/story): routines that fit each
// character, so the calendar and files never tell what the mails do not.

require '/usr/src/roundcubemail/vendor/autoload.php';

use Sabre\VObject;

const DATA = '/var/pond-cloud';
$users = json_decode(file_get_contents('/run/demo/users.json'), true);
$tz = new DateTimeZone(getenv('DEMO_TZ') ?: 'Europe/London');

@mkdir(DATA, 0700, true);
$pdo = new PDO('sqlite:' . DATA . '/dav.sqlite');
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

// sabre/dav 4's SQLite schema (examples/sql/sqlite.*.sql), without its
// example admin principal.
$pdo->exec(<<<'SQL'
CREATE TABLE IF NOT EXISTS principals (id INTEGER PRIMARY KEY ASC NOT NULL, uri TEXT NOT NULL, email TEXT, displayname TEXT, UNIQUE(uri));
CREATE TABLE IF NOT EXISTS groupmembers (id INTEGER PRIMARY KEY ASC NOT NULL, principal_id INTEGER NOT NULL, member_id INTEGER NOT NULL, UNIQUE(principal_id, member_id));
CREATE TABLE IF NOT EXISTS addressbooks (id integer primary key asc NOT NULL, principaluri text NOT NULL, displayname text, uri text NOT NULL, description text, synctoken integer DEFAULT 1 NOT NULL, UNIQUE(principaluri, uri));
CREATE TABLE IF NOT EXISTS cards (id integer primary key asc NOT NULL, addressbookid integer NOT NULL, carddata blob, uri text NOT NULL, lastmodified integer, etag text, size integer, UNIQUE(addressbookid, uri));
CREATE TABLE IF NOT EXISTS addressbookchanges (id integer primary key asc NOT NULL, uri text, synctoken integer NOT NULL, addressbookid integer NOT NULL, operation integer NOT NULL);
CREATE INDEX IF NOT EXISTS addressbookid_synctoken ON addressbookchanges (addressbookid, synctoken);
CREATE TABLE IF NOT EXISTS calendarobjects (id integer primary key asc NOT NULL, calendardata blob NOT NULL, uri text NOT NULL, calendarid integer NOT NULL, lastmodified integer NOT NULL, etag text NOT NULL, size integer NOT NULL, componenttype text, firstoccurence integer, lastoccurence integer, uid text, UNIQUE(calendarid,uri));
CREATE INDEX IF NOT EXISTS calendarid_time ON calendarobjects (calendarid, firstoccurence);
CREATE TABLE IF NOT EXISTS calendars (id integer primary key asc NOT NULL, synctoken integer DEFAULT 1 NOT NULL, components text NOT NULL);
CREATE TABLE IF NOT EXISTS calendarinstances (id integer primary key asc NOT NULL, calendarid integer NOT NULL, principaluri text NULL, access integer NOT NULL DEFAULT '1', displayname text, uri text NOT NULL, description text, calendarorder integer, calendarcolor text, timezone text, transparent bool, share_href text, share_displayname text, share_invitestatus integer DEFAULT '2', UNIQUE (principaluri, uri), UNIQUE (calendarid, principaluri), UNIQUE (calendarid, share_href));
CREATE TABLE IF NOT EXISTS calendarchanges (id integer primary key asc NOT NULL, uri text, synctoken integer NOT NULL, calendarid integer NOT NULL, operation integer NOT NULL);
CREATE INDEX IF NOT EXISTS calendarid_synctoken ON calendarchanges (calendarid, synctoken);
CREATE TABLE IF NOT EXISTS calendarsubscriptions (id integer primary key asc NOT NULL, uri text NOT NULL, principaluri text NOT NULL, source text NOT NULL, displayname text, refreshrate text, calendarorder integer, calendarcolor text, striptodos bool, stripalarms bool, stripattachments bool, lastmodified int, UNIQUE(principaluri, uri));
CREATE TABLE IF NOT EXISTS schedulingobjects (id integer primary key asc NOT NULL, principaluri text NOT NULL, calendardata blob, uri text NOT NULL, lastmodified integer, etag text NOT NULL, size integer NOT NULL, UNIQUE(principaluri, uri));
SQL);

// As in demo/story/characters.yaml and tools/demo (DOMAIN): copied, as PHP
// here has no YAML parser; change them together.
$names = ['croc' => 'Croc', 'otter' => 'Otter', 'tim' => 'TIM', 'brog' => 'brog'];
$domain = 'pond.test';

// Routine appointments: [summary, weekday (1 = Monday), start, minutes,
// RRULE or null]. Character, never plot: nothing here tells what the mails
// do not (demo/story/BIBLE.md). Append only: an appointment's place in its
// list is part of its UID.
$routine = [
    'croc'  => [['Check the backups', 3, '08:00', 15, 'FREQ=WEEKLY'],
                ['Coffee delivery (BeanThere)', 5, '08:00', 15, 'FREQ=WEEKLY'],
                ['Call Mum', 7, '18:00', 30, 'FREQ=WEEKLY'],
                ['Go to bed (before 03:00)', 1, '23:30', 30, 'FREQ=DAILY']],
    'otter' => [['Risk register review', 5, '14:00', 60, 'FREQ=WEEKLY'],
                ['Yoga', 2, '07:00', 60, 'FREQ=WEEKLY'],
                ['Archery class', 4, '18:30', 90, 'FREQ=WEEKLY'],
                ['Predictions: check which came true', 1, '08:00', 30, 'FREQ=WEEKLY'],
                ['Bees with Mags', 6, '10:00', 180, 'FREQ=MONTHLY;BYDAY=1SA']],
    'tim'   => [['Sales pipeline review', 4, '10:00', 30, 'FREQ=WEEKLY'],
                ['Customer call', 2, '11:00', 45, null],
                ['Networking breakfast!!', 3, '07:30', 60, 'FREQ=WEEKLY'],
                ['Update job title', 5, '16:30', 15, 'FREQ=WEEKLY'],
                ['Gym (new me)', 1, '06:30', 45, 'FREQ=WEEKLY;BYDAY=MO,TH']],
    'brog'  => [['Water the office plants', 2, '08:30', 20, 'FREQ=WEEKLY;BYDAY=TU,FR'],
                ['Dr Hartley-Moss', 2, '17:00', 50, 'FREQ=WEEKLY'],
                ['Check the fog', 1, '06:45', 10, 'FREQ=DAILY'],
                ['Talk to the ficus', 3, '12:30', 15, 'FREQ=WEEKLY']],
];
$monday = new DateTimeImmutable('monday this week', $tz);

$caldav = new Sabre\CalDAV\Backend\PDO($pdo);
$carddav = new Sabre\CardDAV\Backend\PDO($pdo);

// Appointments: also for users seeded earlier, so a new routine appointment
// reaches a running demo on its next start (one the user deleted returns).
function seed_appointments($caldav, $user, $events, $monday, $domain)
{
    foreach ($caldav->getCalendarsForUser("principals/users/$user") as $calendar) {
        if ($calendar['uri'] !== 'personal') {
            continue;
        }
        foreach ($events as $i => [$summary, $weekday, $time, $minutes, $rrule]) {
            $uid = "pond-cloud-$user-$i@$domain";
            if ($caldav->getCalendarObject($calendar['id'], "$uid.ics")) {
                continue;
            }
            $start = $monday->modify('+' . ($weekday - 1) . " days $time");
            $vcal = new VObject\Component\VCalendar([
                'VEVENT' => ['UID' => $uid, 'SUMMARY' => $summary, 'DTSTART' => $start,
                             'DTEND' => $start->modify("+$minutes minutes")],
            ]);
            if ($rrule) {
                $vcal->VEVENT->add('RRULE', $rrule);
            }
            $caldav->createCalendarObject($calendar['id'], "$uid.ics", $vcal->serialize());
        }
    }
}

foreach ($users as $user => $password) {
    $events = array_merge([['Pond stand-up', 1, '09:30', 15, 'FREQ=WEEKLY;BYDAY=MO,WE']], $routine[$user] ?? []);
    $principal = "principals/users/$user";
    $exists = $pdo->prepare('SELECT 1 FROM principals WHERE uri = ?');
    $exists->execute([$principal]);
    if ($exists->fetchColumn()) {
        seed_appointments($caldav, $user, $events, $monday, $domain);
        continue;
    }
    $pdo->prepare('INSERT INTO principals (uri, email, displayname) VALUES (?, ?, ?)')
        ->execute([$principal, "$user@$domain", $names[$user] ?? $user]);

    // Calendar, named as Nextcloud names its default one.
    $caldav->createCalendar($principal, 'personal', [
        '{DAV:}displayname' => 'Personal',
        '{http://apple.com/ns/ical/}calendar-color' => '#0082c9',
    ]);
    seed_appointments($caldav, $user, $events, $monday, $domain);
    // A second, empty one after it: Nextcloud's default calendar (personal)
    // must win over list order when the webmail preselects one.
    $caldav->createCalendar($principal, 'projects', [
        '{DAV:}displayname' => 'Projects',
        '{http://apple.com/ns/ical/}calendar-color' => '#46ba61',
    ]);

    // Addressbook with the colleagues, named as Nextcloud names its default.
    $book = $carddav->createAddressBook($principal, 'contacts', ['{DAV:}displayname' => 'Contacts']);
    $colleagues = $names + ['management' => 'The Management'];
    foreach ($colleagues as $who => $name) {
        if ($who === $user) {
            continue;
        }
        $card = new VObject\Component\VCard(['FN' => $name, 'N' => [$name, '', '', '', ''],
            'EMAIL' => "$who@$domain", 'ORG' => 'Pond Ltd', 'UID' => "pond-cloud-$who@$domain"]);
        $carddav->createCard($book, "$who.vcf", $card->serialize());
    }

    // Files.
    $home = DATA . "/files/$user";
    @mkdir("$home/Documents", 0700, true);
    @mkdir("$home/Photos", 0700, true);
    file_put_contents("$home/Documents/Welcome to Pond Cloud.txt",
        "Welcome to Pond Cloud, the Pond Ltd file store.\n\n"
        . "Put files here to attach them to mail, and save attachments here from\n"
        . "the webmail. Your calendar and contacts live here too.\n");
    file_put_contents("$home/Documents/Office handbook.txt",
        "Pond Ltd -- Office handbook (abridged)\n\n"
        . "1. The kettle is a shared resource.\n"
        . "2. Stand-up is on Mondays and Wednesdays at 09:30. Sitting is permitted.\n"
        . "3. The pond in reception is not a water feature for testing.\n");
}
echo "pond-cloud: seeded for " . implode(', ', array_keys($users)) . "\n";
