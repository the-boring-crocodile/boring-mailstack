"""The files of a home's etc/, as tools/setup and tools/demo write them,
and how tools read them back (read_env).

Imported by tools/setup, tools/demo and tools/deploy (with bytecode writing
off: a release tree must stay exactly as its manifest lists it).
"""
import secrets


def read_env(path):
    """KEY=value lines of an env file; one pair of surrounding quotes is
    removed, as Compose does."""
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def write(path, text, mode=0o600):
    """A file only its owner can read (etc/ holds every secret)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def bridge_env():
    """etc/bridge.env: the password of the bridge's Stalwart account (init
    creates it; the rest of its login is fixed in compose.yaml)."""
    return f"JMAP_PASSWORD={secrets.token_hex(18)}\n"


def roundcube_config(product_name, mail_domain, header, extra=""):
    """etc/roundcube/config.inc.php. The image adds Filters, Contacts,
    Calendar and cloud files on top (roundcube/mailstack-defaults.inc.php)."""
    return f"""<?php
// {header}
$config['product_name'] = '{product_name}';
$config['imap_host'] = 'ssl://stalwart.mailstack.local:993';
$config['smtp_host'] = 'ssl://stalwart.mailstack.local:465';
$config['smtp_user'] = '%u';
$config['smtp_pass'] = '%p';
// Inside the stack Stalwart's certificate is self-signed (DECISIONS.md, TLS).
$config['imap_conn_options'] = [
    'ssl' => ['verify_peer' => false, 'verify_peer_name' => false, 'allow_self_signed' => true],
];
$config['smtp_conn_options'] = $config['imap_conn_options'];
// Domain of a new user's identity when the login has none (users log in
// with their address, so normally unused).
$config['mail_domain'] = '{mail_domain}';
// Encrypts the IMAP password and the Nextcloud session in Roundcube's
// session table. Keep it: changing it logs everyone out.
$config['des_key'] = '{secrets.token_urlsafe(18)[:24]}';
{extra}"""


def stack_env(bind, webmail_port, admin_port, extra_lines=()):
    """etc/.env: Stalwart's admin password and where the two web pages
    listen. Returns (text, admin password)."""
    admin = secrets.token_hex(18)
    lines = [*extra_lines,
             f"STALWART_RECOVERY_ADMIN=admin:{admin}",
             f"STALWART_ADMIN_PASSWORD={admin}",
             f"STALWART_ADMIN_BIND={bind}",
             f"STALWART_ADMIN_PORT={admin_port}",
             f"ROUNDCUBE_BIND={bind}",
             f"ROUNDCUBE_PORT={webmail_port}"]
    return "\n".join(lines) + "\n", admin
