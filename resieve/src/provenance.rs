use rusqlite::{Connection, OpenFlags};
use std::{
    collections::BTreeSet,
    process,
};

pub fn load_protected(
    path: &str,
    account: &str,
) -> BTreeSet<String> {
    let db = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )
    .unwrap_or_else(|error| {
        eprintln!(
            "failed to open provenance database {}: {}",
            path, error
        );
        process::exit(1);
    });

    let mut statement = db
        .prepare(
            r#"
            SELECT email_id
            FROM protected_email
            WHERE account = ?1
            "#,
        )
        .unwrap_or_else(|error| {
            eprintln!("failed to prepare provenance query: {error}");
            process::exit(1);
        });

    let rows = statement
        .query_map([account], |row| row.get::<_, String>(0))
        .unwrap_or_else(|error| {
            eprintln!("failed to query provenance database: {error}");
            process::exit(1);
        });

    let mut protected = BTreeSet::new();

    for row in rows {
        protected.insert(row.unwrap_or_else(|error| {
            eprintln!("failed to read provenance row: {error}");
            process::exit(1);
        }));
    }

    protected
}

// Delete exactly these ids: mail Stalwart reported gone (notFound), or mail
// released to the filter by a re-sort.
pub fn remove(
    path: &str,
    account: &str,
    gone: &BTreeSet<String>,
) -> usize {
    let mut db = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .unwrap_or_else(|error| {
        eprintln!(
            "failed to open provenance database {} for cleanup: {}",
            path, error
        );
        process::exit(1);
    });

    let tx = db.transaction().unwrap_or_else(|error| {
        eprintln!("failed to begin provenance cleanup: {error}");
        process::exit(1);
    });

    let mut removed = 0usize;
    for email_id in gone {
        removed += tx
            .execute(
                "DELETE FROM protected_email WHERE account = ?1 AND email_id = ?2",
                rusqlite::params![account, email_id],
            )
            .unwrap_or_else(|error| {
                eprintln!("failed to remove provenance {}/{}: {}", account, email_id, error);
                process::exit(1);
            });
    }

    tx.commit().unwrap_or_else(|error| {
        eprintln!("failed to commit provenance cleanup: {error}");
        process::exit(1);
    });

    removed
}
