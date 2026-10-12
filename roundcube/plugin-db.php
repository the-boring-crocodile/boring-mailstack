<?php
// boring-mailstack: create or update the database tables of plugins that
// bring their own SQL (Roundcube's entrypoint only handles its core schema).
// Run on every start as an entrypoint post-setup task, before the database
// is handed to www-data (50-mailstack-db-owner). Idempotent.
define('INSTALL_PATH', '/var/www/html/');
require INSTALL_PATH . 'program/include/clisetup.php';

$packages = [
    'libkolab'        => 'plugins/libkolab/SQL',
    'calendar-caldav' => 'plugins/calendar/drivers/caldav/SQL',
];
$db = rcmail_utils::db();
foreach ($packages as $package => $dir) {
    if (!is_dir(INSTALL_PATH . $dir)) {
        fwrite(STDERR, "mailstack: $package: no SQL in $dir (the image is built with it)\n");
        exit(1);
    }
    $res = $db->query('SELECT value FROM ' . $db->table_name('system', true) . ' WHERE name = ?', "$package-version");
    $row = $res ? $db->fetch_assoc($res) : null;
    if (!$row) {
        echo "mailstack: creating tables for $package\n";
        // Statement by statement, stopping at the first error. (Databases
        // made while libkolab's schema named two indexes alike were made
        // skipping that one; patches/kolab/2-kolab-sqlite-index fixes the
        // schema, and its 2026100700 update adds the index to them.)
        $file = INSTALL_PATH . $dir . '/' . $db->db_provider . '.initial.sql';
        $sql = preg_replace('/^--.*$/m', '', file_get_contents($file));
        foreach (array_filter(array_map('trim', explode(";\n", $sql))) as $statement) {
            if (!$db->query($statement) && $db->is_error()) {
                fwrite(STDERR, "mailstack: $package: " . $db->is_error() . "\n");
                exit(1);
            }
        }
    } else {
        echo "mailstack: updating tables for $package (at {$row['value']})\n";
        rcmail_utils::db_update(INSTALL_PATH . $dir, $package);
    }
}
