use std::{env, process};

pub const DEFAULT_PROTECTED: &[&str] = &["Sent", "Drafts", "Trash", "Junk"];

pub struct Config {
    pub username: String,
    pub password: String,
    pub account: String,
    pub provenance_path: String,
    pub url: String,
    pub limit: Option<usize>,
    pub mailbox_filter: Option<String>,
    pub apply: bool,
    pub full_messages: bool,
    /// Folders resieve never takes a message out of (roles or paths).
    pub protected_folders: Vec<String>,
    /// Re-sort chute (RESIEVE_RESORT_IDS_FILE): only these mails, which a human
    /// moved into INBOX (or a resievable Junk): released and sorted again;
    /// no rule matches -> they stay where they are.
    pub resort_ids: Option<Vec<String>>,
    /// Set by the account (not the default): every entry must exist.
    pub protected_explicit: bool,
}

impl Config {
    pub fn from_env() -> Self {
        let limit = env::var("RESIEVE_LIMIT")
            .ok()
            .map(|value| {
                value.parse::<usize>().unwrap_or_else(|error| {
                    eprintln!(
                        "invalid RESIEVE_LIMIT {:?}: {}",
                        value, error
                    );
                    process::exit(2);
                })
            });
        if limit == Some(0) {
            eprintln!("invalid RESIEVE_LIMIT 0 (unset it for no limit)");
            process::exit(2);
        }

        let mailbox_filter = env::var("RESIEVE_MAILBOX")
            .ok()
            .filter(|value| !value.is_empty());

        let apply = match env::var("RESIEVE_APPLY").ok().as_deref() {
            None | Some("") | Some("0") => false,
            Some("1") => true,
            Some(value) => {
                eprintln!(
                    "resieve: RESIEVE_APPLY must be 0 or 1, got {:?}",
                    value
                );
                process::exit(2);
            }
        };

        // Always download whole messages, even for a script that reads only
        // header fields (comparison runs, or if in doubt).
        let full_messages = matches!(
            env::var("RESIEVE_FULL_MESSAGES").ok().as_deref(),
            Some("1")
        );

        // Unset: the safe default; set but empty: none.
        let protected_folders = match env::var("RESIEVE_PROTECTED_FOLDERS") {
            Err(_) => DEFAULT_PROTECTED.iter().map(|s| s.to_string()).collect(),
            Ok(value) => value
                .split(|c| c == ',' || c == '\n')
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map(str::to_string)
                .collect(),
        };

        Self {
            username: required_env("RESIEVE_USERNAME"),
            password: required_env("RESIEVE_PASSWORD"),
            account: required_env("RESIEVE_ACCOUNT"),
            provenance_path: required_env("RESIEVE_PROVENANCE_DB"),
            // The session URL itself: jmap-client 0.4.2 rejects Stalwart's
            // same-host relative /.well-known/jmap redirect.
            url: required_env("RESIEVE_URL"),
            limit,
            mailbox_filter,
            apply,
            full_messages,
            protected_explicit: env::var("RESIEVE_PROTECTED_FOLDERS").is_ok(),
            protected_folders,
            // One id per line (resieve-watch writes the file).
            resort_ids: env::var("RESIEVE_RESORT_IDS_FILE")
                .ok()
                .map(|path| {
                    std::fs::read_to_string(&path).unwrap_or_else(|error| {
                        eprintln!("RESIEVE_RESORT_IDS_FILE {path}: {error}");
                        std::process::exit(2);
                    })
                })
                .map(|value| {
                    value
                        .split(|c: char| c == ',' || c.is_whitespace())
                        .filter(|s| !s.is_empty())
                        .map(str::to_string)
                        .collect()
                }),
        }
    }
}

fn required_env(name: &str) -> String {
    match env::var(name) {
        Ok(value) if !value.is_empty() => value,
        _ => {
            eprintln!("missing required environment variable: {name}");
            process::exit(2);
        }
    }
}
