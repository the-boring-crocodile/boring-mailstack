use jmap_client::{
    client::Client,
    mailbox,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    process,
};

// Stable translation between human/Sieve mailbox paths and JMAP
// mailbox IDs. Protocol-specific path normalization belongs here so
// the resieve algorithm does not need to know JMAP/IMAP naming details.
pub struct MailboxMap {
    path_to_id: BTreeMap<String, String>,
    id_to_path: BTreeMap<String, String>,
    /// JMAP role (lower case: inbox, sent, drafts, trash, junk, archive, ...)
    /// to mailbox ID.
    role_to_id: BTreeMap<String, String>,
}

impl MailboxMap {
    pub fn load(client: &Client) -> Self {
        let mut query = client
            .mailbox_query(
                None::<mailbox::query::Filter>,
                None::<Vec<_>>,
            )
            .expect("Mailbox/query failed");

        let mailbox_ids = query.take_ids();
        let mut names = BTreeMap::<String, String>::new();
        let mut parents = BTreeMap::<String, Option<String>>::new();
        let mut roles = BTreeMap::<String, String>::new();

        for mailbox_id in &mailbox_ids {
            let mailbox = client
                .mailbox_get(
                    mailbox_id,
                    [
                        mailbox::Property::Name,
                        mailbox::Property::ParentId,
                        mailbox::Property::Role,
                    ]
                    .into(),
                )
                .expect("Mailbox/get failed")
                .unwrap_or_else(|| {
                    eprintln!(
                        "mailbox disappeared id={}",
                        mailbox_id
                    );
                    process::exit(1);
                });

            let name = mailbox
                .name()
                .unwrap_or_else(|| {
                    eprintln!(
                        "mailbox has no name id={}",
                        mailbox_id
                    );
                    process::exit(1);
                })
                .to_string();

            let role = match mailbox.role() {
                mailbox::Role::Archive => Some("archive".to_string()),
                mailbox::Role::Drafts => Some("drafts".to_string()),
                mailbox::Role::Important => Some("important".to_string()),
                mailbox::Role::Inbox => Some("inbox".to_string()),
                mailbox::Role::Junk => Some("junk".to_string()),
                mailbox::Role::Sent => Some("sent".to_string()),
                mailbox::Role::Trash => Some("trash".to_string()),
                mailbox::Role::Other(other) => Some(other.to_ascii_lowercase()),
                mailbox::Role::None => None,
            };
            if let Some(role) = role {
                roles.insert(role, mailbox_id.clone());
            }
            names.insert(mailbox_id.clone(), name);
            parents.insert(
                mailbox_id.clone(),
                mailbox.parent_id().map(str::to_string),
            );
        }

        let entries = mailbox_ids
            .iter()
            .map(|id| {
                (
                    id.clone(),
                    names[id].clone(),
                    parents.get(id).cloned().flatten(),
                )
            })
            .collect::<Vec<_>>();

        let mut map = Self::from_entries(&entries).unwrap_or_else(|error| {
            eprintln!("{error}");
            process::exit(1);
        });
        map.role_to_id = roles;
        map
    }

    /// The folder with this JMAP role (inbox, junk, ...).
    pub fn role_id(&self, role: &str) -> Option<&str> {
        self.role_to_id.get(role).map(String::as_str)
    }

    /// A folder given by role (Sent, Drafts, Trash, Junk, Archive, Inbox;
    /// any case) or by path.
    pub fn ids_for_spec(&self, spec: &str) -> BTreeSet<&str> {
        // Both: a role-less folder literally named like the spec is meant
        // as much as the folder that carries the role.
        let mut ids = BTreeSet::new();
        if let Some(id) = self.role_to_id.get(&spec.to_ascii_lowercase()) {
            ids.insert(id.as_str());
        }
        if let Some(id) = self.id_for_sieve_path(spec) {
            ids.insert(id);
        }
        ids
    }

    /// Paths from (id, name, parent id) entries: names joined with "/"
    /// from the root down. A parent cycle, an unknown parent or two
    /// mailboxes with the same path is an error.
    pub fn from_entries(
        entries: &[(String, String, Option<String>)],
    ) -> Result<Self, String> {
        let names: BTreeMap<&str, &str> = entries
            .iter()
            .map(|(id, name, _)| (id.as_str(), name.as_str()))
            .collect();
        let parents: BTreeMap<&str, Option<&str>> = entries
            .iter()
            .map(|(id, _, parent)| (id.as_str(), parent.as_deref()))
            .collect();

        let mut path_to_id = BTreeMap::new();
        let mut id_to_path = BTreeMap::new();

        for (mailbox_id, _, _) in entries {
            let mut parts = Vec::new();
            let mut current = Some(mailbox_id.as_str());
            let mut seen = BTreeSet::new();

            while let Some(id) = current {
                if !seen.insert(id) {
                    return Err(format!(
                        "mailbox parent cycle detected at id={id}"
                    ));
                }

                let name = names.get(id).ok_or_else(|| {
                    format!("unknown mailbox id while building path: {id}")
                })?;

                parts.push(*name);
                current = parents.get(id).copied().flatten();
            }

            parts.reverse();
            let path = parts.join("/");

            if let Some(previous) =
                path_to_id.insert(path.clone(), mailbox_id.clone())
            {
                return Err(format!(
                    "duplicate mailbox path {path:?}: ids {previous} and {mailbox_id}"
                ));
            }

            id_to_path.insert(mailbox_id.clone(), path);
        }

        Ok(Self {
            path_to_id,
            id_to_path,
            role_to_id: BTreeMap::new(),
        })
    }

    /// A folder resieve has just created.
    pub fn insert(&mut self, id: &str, path: &str) {
        self.path_to_id.insert(path.to_string(), id.to_string());
        self.id_to_path.insert(id.to_string(), path.to_string());
    }

    pub fn len(&self) -> usize {
        self.path_to_id.len()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.path_to_id
            .iter()
            .map(|(path, id)| (path.as_str(), id.as_str()))
    }

    pub fn id_for_path(&self, path: &str) -> Option<&str> {
        self.path_to_id.get(path).map(String::as_str)
    }

    pub fn path_for_id(&self, id: &str) -> Option<&str> {
        self.id_to_path.get(id).map(String::as_str)
    }

    pub fn id_for_sieve_path(&self, path: &str) -> Option<&str> {
        // IMAP/Sieve INBOX is case-insensitive. Child mailbox names
        // retain their original case.
        if path.eq_ignore_ascii_case("INBOX") {
            return self
                .role_to_id
                .get("inbox")
                .map(String::as_str)
                .or_else(|| self.id_for_path("Inbox"));
        }

        if let Some(rest) = path
            .get(..6)
            .filter(|p| p.eq_ignore_ascii_case("INBOX/"))
            .map(|_| &path[6..])
        {
            let normalized = format!("Inbox/{rest}");
            return self.id_for_path(&normalized);
        }

        self.id_for_path(path)
    }
}

#[cfg(test)]
mod tests {
    use super::MailboxMap;

    fn entry(id: &str, name: &str, parent: Option<&str>) -> (String, String, Option<String>) {
        (id.to_string(), name.to_string(), parent.map(str::to_string))
    }

    fn sample() -> MailboxMap {
        MailboxMap::from_entries(&[
            entry("a", "Inbox", None),
            entry("b", "Receipts", None),
            entry("c", "Coffee", Some("b")),
            entry("d", "Lists", Some("a")),
            entry("e", "Gran's 90th 🎉", Some("c")),
        ])
        .unwrap()
    }

    #[test]
    fn nested_paths() {
        let map = sample();
        assert_eq!(map.len(), 5);
        assert_eq!(map.id_for_path("Receipts/Coffee"), Some("c"));
        assert_eq!(map.id_for_path("Receipts/Coffee/Gran's 90th 🎉"), Some("e"));
        assert_eq!(map.path_for_id("d"), Some("Inbox/Lists"));
        assert_eq!(map.id_for_path("Coffee"), None);
    }

    #[test]
    fn sieve_inbox_names() {
        let map = sample();
        assert_eq!(map.id_for_sieve_path("INBOX"), Some("a"));
        assert_eq!(map.id_for_sieve_path("INBOX/Lists"), Some("d"));
        assert_eq!(map.id_for_sieve_path("Inbox/Lists"), Some("d"));
        assert_eq!(map.id_for_sieve_path("Receipts/Coffee"), Some("c"));
        assert_eq!(map.id_for_sieve_path("receipts/coffee"), None);
    }

    #[test]
    fn cycle_is_an_error() {
        let error = MailboxMap::from_entries(&[
            entry("x", "X", Some("y")),
            entry("y", "Y", Some("x")),
        ])
        .err()
        .unwrap();
        assert!(error.contains("cycle"), "{error}");
    }

    #[test]
    fn unknown_parent_is_an_error() {
        let error = MailboxMap::from_entries(&[entry("x", "X", Some("gone"))])
            .err()
            .unwrap();
        assert!(error.contains("unknown mailbox id"), "{error}");
    }

    #[test]
    fn duplicate_path_is_an_error() {
        let error = MailboxMap::from_entries(&[
            entry("x", "Same", None),
            entry("y", "Same", None),
        ])
        .err()
        .unwrap();
        assert!(error.contains("duplicate mailbox path"), "{error}");
    }

    #[test]
    fn spec_matches_role_and_name() {
        let mut map = MailboxMap::from_entries(&[
            entry("i", "Inbox", None),
            entry("j", "Junk Mail", None),
            entry("k", "Junk", None),
            entry("s", "Sent Items", None),
        ])
        .unwrap();
        map.role_to_id.insert("junk".into(), "j".into());
        map.role_to_id.insert("inbox".into(), "i".into());
        let ids: Vec<&str> = map.ids_for_spec("Junk").into_iter().collect();
        assert_eq!(ids, vec!["j", "k"]);
        assert!(map.ids_for_spec("Sent").is_empty());
        assert_eq!(map.ids_for_spec("Sent Items").into_iter().collect::<Vec<_>>(), vec!["s"]);
        assert_eq!(map.id_for_sieve_path("inbox"), Some("i"));
    }
}
