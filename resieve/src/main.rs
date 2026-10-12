use jmap_client::{
    client::Client,
    email,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    process,
    time::Instant,
};

mod config;
mod download;
mod mailboxes;
mod provenance;
mod script_scope;
mod sieve_engine;
mod throttle;

use config::Config;
use download::{Downloader, SetError};
use mailboxes::MailboxMap;
use sieve_engine::{SieveEngine, SieveResult};


struct RunStats {
    evaluated: usize,
    finished: usize,
    pending: usize,
    errors: usize,
    protected: usize,
    seen_protected: BTreeSet<String>,
    planned_preserve: usize,
    already_correct: usize,
    would_move: usize,
    applied_moves: usize,
    mutation_errors: usize,
    unresolved_destination: usize,
    in_protected_folder: usize,
    no_placement: usize,
    stays_no_rule: usize,
    skipped_at_apply: usize,
    transitions: BTreeMap<String, usize>,
}

impl RunStats {
    fn new() -> Self {
        Self {
            evaluated: 0,
            finished: 0,
            pending: 0,
            errors: 0,
            protected: 0,
            seen_protected: BTreeSet::new(),
            planned_preserve: 0,
            already_correct: 0,
            would_move: 0,
            applied_moves: 0,
            mutation_errors: 0,
            unresolved_destination: 0,
            in_protected_folder: 0,
            no_placement: 0,
            stays_no_rule: 0,
            skipped_at_apply: 0,
            transitions: BTreeMap::new(),
        }
    }

    fn run_ok(
        &self,
        evaluation_target: usize,
        apply: bool,
    ) -> bool {
        self.evaluated == evaluation_target
            && self.pending == 0
            && self.errors == 0
            && self.unresolved_destination == 0
            && (!apply || self.applied_moves + self.skipped_at_apply == self.would_move)
    }
}


/// What resieve changes for one message: it ends up exactly where the
/// filter puts it (the caller has already skipped protected mail, mail in a
/// protected folder and mail the filter places nowhere). None: nothing to
/// change.
fn plan(
    current: &BTreeSet<String>,
    desired: &BTreeSet<String>,
) -> Option<(BTreeSet<String>, BTreeSet<String>)> {
    let add: BTreeSet<String> = desired.difference(current).cloned().collect();
    let remove: BTreeSet<String> = current.difference(desired).cloned().collect();
    if add.is_empty() && remove.is_empty() {
        None
    } else {
        Some((add, remove))
    }
}

struct Rules<'a> {
    protected_folders: &'a BTreeSet<String>,
    /// Re-sort chute run: the mails were released (no provenance check).
    resort: bool,
    /// INBOX, and Junk when it may be re-sorted: a re-sort touches a mail
    /// only while it is still in one of these.
    chute: &'a BTreeSet<String>,
    provenance_path: &'a str,
    account: &'a str,
}

/// One planned change: the mail's new folders, whether its junk flag goes
/// (a rule of the user's filter overruled the spam verdict), and a human's
/// verdict to record (re-sort, no rule: into Junk = spam, into INBOX = not
/// spam), so the next filter change keeps it.
struct Move {
    id: String,
    desired: BTreeSet<String>,
    clear_junk: bool,
    verdict: Option<bool>,
}

/// Write attempts for a page of moves, with the pause before each retry and
/// the batch size: smaller batches leave less time between looking and
/// writing. The last attempt writes without ifInState: the writes only add
/// and remove folders, so the worst race leaves a mail in one folder more.
const ATTEMPTS: [(u64, usize); 10] = [
    (0, 500), (1, 100), (2, 100), (4, 20), (8, 20), (16, 20), (30, 20), (30, 20), (30, 20), (30, 20),
];

/// Applies a page's moves, after looking again: the protected list is
/// re-read, each mail's folders are fetched fresh, and the write carries
/// ifInState, so a change in between is not overwritten (Stalwart answers
/// stateMismatch; that batch is looked at again).
fn apply_moves(
    downloader: &Downloader,
    moves: &[Move],
    rules: &Rules,
    stats: &mut RunStats,
) {
    let mut pending: Vec<&Move> = moves.iter().collect();
    for (attempt, (pause, size)) in ATTEMPTS.iter().enumerate() {
        if pending.is_empty() {
            return;
        }
        if *pause > 0 {
            println!("resieve: mailbox changed during the run; {} moves again in {} s", pending.len(), pause);
            std::thread::sleep(std::time::Duration::from_secs(*pause));
        }
        let last = attempt == ATTEMPTS.len() - 1;
        let mut again = Vec::new();
        for chunk in pending.chunks(*size) {
            if !apply_chunk(downloader, chunk, rules, stats, !last) {
                again.extend_from_slice(chunk);
            }
        }
        pending = again;
    }
}

/// false: the account changed in between (stateMismatch); try again.
fn apply_chunk(
    downloader: &Downloader,
    moves: &[&Move],
    rules: &Rules,
    stats: &mut RunStats,
    use_state: bool,
) -> bool {
    let ids: Vec<String> = moves.iter().map(|m| m.id.clone()).collect();
    let protected_now = if rules.resort {
        BTreeSet::new()      // released by this run
    } else {
        provenance::load_protected(rules.provenance_path, rules.account)
    };
    let membership = match downloader.membership(&ids) {
        Ok(m) => m,
        Err(error) => {
            stats.errors += moves.len();
            stats.mutation_errors += moves.len();
            eprintln!("resieve: Email/get before Email/set failed: {error}");
            return true;
        }
    };

    let mut updates = serde_json::Map::new();
    let mut skipped = 0;
    for m in moves {
        let current: BTreeSet<String> = match membership.mailbox_ids.get(&m.id) {
            Some(ids) => ids.iter().cloned().collect(),
            None => {
                skipped += 1;       // gone meanwhile
                continue;
            }
        };
        if protected_now.contains(&m.id)
            || current.iter().any(|id| rules.protected_folders.contains(id))
            || (rules.resort && !current.iter().any(|id| rules.chute.contains(id)))
        {
            skipped += 1;           // protected, or moved out of the chute, meanwhile
            continue;
        }
        let mut patch = serde_json::Map::new();
        if let Some((add, remove)) = plan(&current, &m.desired) {
            for id in add {
                patch.insert(format!("mailboxIds/{id}"), serde_json::json!(true));
            }
            for id in remove {
                patch.insert(format!("mailboxIds/{id}"), serde_json::Value::Null);
            }
        }
        if m.clear_junk {
            patch.insert("keywords/$junk".into(), serde_json::Value::Null);
        }
        match m.verdict {
            Some(true) => {
                patch.insert("keywords/$junk".into(), serde_json::json!(true));
                patch.insert("keywords/$notjunk".into(), serde_json::Value::Null);
            }
            Some(false) => {
                patch.insert("keywords/$notjunk".into(), serde_json::json!(true));
                patch.insert("keywords/$junk".into(), serde_json::Value::Null);
            }
            None => {}
        }
        if patch.is_empty() {
            skipped += 1;           // already where it belongs
        } else {
            updates.insert(m.id.clone(), serde_json::Value::Object(patch));
        }
    }

    if updates.is_empty() {
        stats.skipped_at_apply += skipped;
        return true;
    }

    let state = if use_state { Some(membership.state.as_str()) } else { None };
    match downloader.email_set(&updates, state) {
        Ok(result) => {
            stats.skipped_at_apply += skipped;
            for id in updates.keys() {
                if result.updated.contains(id) {
                    stats.applied_moves += 1;
                } else {
                    stats.errors += 1;
                    stats.mutation_errors += 1;
                    eprintln!("resieve: Email/set failed id={} error={}", id,
                              result.not_updated.get(id).map(String::as_str).unwrap_or("not updated"));
                }
            }
            true
        }
        Err(SetError::StateMismatch) => false,
        Err(SetError::Other(error)) => {
            stats.skipped_at_apply += skipped;
            stats.errors += updates.len();
            stats.mutation_errors += updates.len();
            eprintln!("resieve: Email/set of {} moves failed: {}", updates.len(), error);
            true
        }
    }
}


/// The id of a folder `fileinto :create` names, made (with its parents)
/// when missing; in a dry run a placeholder.
fn ensure_folder(
    downloader: &Downloader,
    mailboxes: &mut MailboxMap,
    path: &str,
    apply: bool,
) -> Result<String, String> {
    if let Some(id) = mailboxes.id_for_sieve_path(path) {
        return Ok(id.to_string());
    }
    if !apply {
        return Ok(format!("<new:{path}>"));
    }
    let mut parent: Option<String> = None;
    let mut sofar = String::new();
    for part in path.split('/') {
        if !sofar.is_empty() {
            sofar.push('/');
        }
        sofar.push_str(part);
        let id = match mailboxes.id_for_sieve_path(&sofar) {
            Some(id) => id.to_string(),
            None => {
                let id = downloader.mailbox_create(part, parent.as_deref())?;
                println!("resieve: created folder {:?}", sofar);
                mailboxes.insert(&id, &sofar);
                id
            }
        };
        parent = Some(id);
    }
    parent.ok_or_else(|| "empty folder name".to_string())
}

/// Re-sort chute: of the mails a human moved into INBOX (or a resievable
/// Junk), those still there are released (their "placed by a human" record
/// goes, on --apply) and become this run's corpus. The release stands
/// whatever the run's outcome: the move into the chute handed the mail to
/// the filter (DECISIONS.md, re-sort chute); a mail a failed run leaves
/// where it is gets sorted by the filter's next run.
fn release_for_resort(
    config: &Config,
    ids: &[String],
    chute: &BTreeSet<String>,
    protected: &mut BTreeSet<String>,
    downloader: &Downloader,
) -> Vec<String> {
    // In pages: Stalwart answers at most 500 objects per Email/get, and a
    // folder restructure moves many more.
    let mut in_chute: Vec<String> = Vec::new();
    for page in ids.chunks(500) {
        let membership = downloader.membership(page).unwrap_or_else(|error| {
            eprintln!("resieve: Email/get of the re-sort mails failed: {error}");
            process::exit(1);
        });
        in_chute.extend(page.iter().filter(|id| {
            membership
                .mailbox_ids
                .get(*id)
                .map_or(false, |boxes| boxes.iter().any(|b| chute.contains(b)))
        }).cloned());
    }
    println!(
        "resieve: re-sort {} of {} mails (the others are no longer in INBOX/Junk or gone)",
        in_chute.len(),
        ids.len()
    );
    let released: BTreeSet<String> = in_chute.iter().cloned().collect();
    for id in &released {
        protected.remove(id);
    }
    if config.apply && !released.is_empty() {
        let removed = provenance::remove(&config.provenance_path, &config.account, &released);
        println!("resieve: released {removed} mails (no longer marked as placed by a human)");
    }
    in_chute
}

fn main() {
    const PAGE_SIZE: usize = 500;

    let config = Config::from_env();

    let mut protected_email_ids =
        provenance::load_protected(
            &config.provenance_path,
            &config.account,
        );

    println!(
        "resieve: provenance account={} protected={}",
        config.account,
        protected_email_ids.len()
    );


    println!("resieve: connecting");

    // This client talks only to Stalwart on the private Docker
    // network. Stalwart's internal certificate is not rooted in the
    // container's public CA store, so certificate validation is
    // deliberately disabled for this internal connection.
    let client = Client::new()
        .credentials((config.username.as_str(), config.password.as_str()))
        .accept_invalid_certs(true)
        .connect(&config.url)
        .unwrap_or_else(|error| {
            eprintln!("JMAP connection failed: {error:#?}");
            process::exit(1);
        });

    println!(
        "resieve: connected, default account={}",
        client.default_account_id()
    );

    /*
     * Sieve speaks mailbox paths; Email objects speak stable JMAP
     * mailbox IDs. Resolve that translation once for the run.
     */
    let mut mailboxes = MailboxMap::load(&client);

    println!("resieve: mailboxes={}", mailboxes.len());

    for (path, id) in mailboxes.iter() {
        println!("resieve: mailbox {:?} -> {}", path, id);
    }

    let mailbox_filter_id = config.mailbox_filter.as_ref().map(|path| {
        mailboxes
            .id_for_sieve_path(path)
            .unwrap_or_else(|| {
                eprintln!("unknown RESIEVE_MAILBOX {:?}", path);
                process::exit(2);
            })
            .to_string()
    });

    if let Some(path) = &config.mailbox_filter {
        println!(
            "resieve: mailbox filter {:?} -> {}",
            path,
            mailbox_filter_id.as_deref().unwrap()
        );
    }

    let mut sieve = SieveEngine::load(&client);

    let mut protected_folders = BTreeSet::new();
    for spec in &config.protected_folders {
        let ids = mailboxes.ids_for_spec(spec);
        if ids.is_empty() {
            if config.protected_explicit {
                // Fail closed: a typo must not leave a folder unprotected.
                eprintln!(
                    "resieve: protected folder {:?} (resieve.never_move_from in accounts.yaml) matches no role or folder; refusing to run",
                    spec
                );
                process::exit(1);
            }
            println!("resieve: protected folder {:?} does not exist here", spec);
        }
        for id in ids {
            println!(
                "resieve: protected {:?} -> {}",
                spec,
                mailboxes.path_for_id(id).unwrap_or(id)
            );
            protected_folders.insert(id.to_string());
        }
    }
    println!(
        "resieve: never out of: {}",
        if config.protected_folders.is_empty() { "(none)".to_string() } else { config.protected_folders.join(", ") }
    );
    let resort = config.resort_ids.is_some();
    let inbox_id = mailboxes.role_id("inbox").or_else(|| mailboxes.id_for_sieve_path("INBOX")).map(str::to_string);
    let junk_id = mailboxes.role_id("junk").map(str::to_string);
    // Re-sort chute: INBOX, and Junk when it is not in never_move_from.
    let chute: BTreeSet<String> = inbox_id
        .iter()
        .chain(junk_id.iter().filter(|id| !protected_folders.contains(*id)))
        .cloned()
        .collect();
    let rules = Rules {
        protected_folders: &protected_folders,
        resort,
        chute: &chute,
        provenance_path: &config.provenance_path,
        account: &config.account,
    };

    /*
     * First Email/query explicitly asks Stalwart for the total.
     * We use the query builder directly so pagination is explicit.
     */
    let downloader = Downloader::new(&client, &config.username, &config.password)
        .unwrap_or_else(|error| {
            eprintln!("resieve: {error}");
            process::exit(1);
        });

    let started = Instant::now();

    let mut stats = RunStats::new();
    println!(
        "resieve: mode={}",
        if config.apply { "APPLY" } else { "dry-run" }
    );

    // The corpus: a re-sort evaluates only the mails a human moved into the
    // chute; any other run snapshots the (scoped) mailbox first.
    let (corpus_ids, total, evaluation_target, snapshot_consistent) = if let Some(ids) = &config.resort_ids {
        let ids = release_for_resort(&config, ids, &chute, &mut protected_email_ids, &downloader);
        let n = ids.len();
        (ids, n, n, true)
    } else {
        let mut page = throttle::with_retry("Email/query", || {
            let mut request = client.build();
            let query = request.query_email().position(0).limit(PAGE_SIZE).calculate_total(true);
            if let Some(mailbox_id) = &mailbox_filter_id {
                query.filter(email::query::Filter::in_mailbox(mailbox_id));
            }
            request.send_query_email()
        })
        .unwrap_or_else(|error| {
            eprintln!("resieve: initial Email/query failed: {error:?}");
            process::exit(1);
        });

        let total = page.total().unwrap_or_else(|| {
            eprintln!("resieve: Stalwart did not return the Email/query total");
            process::exit(1);
        });

        let evaluation_target = config.limit
            .map(|value| value.min(total))
            .unwrap_or(total);

        println!(
            "resieve: corpus total={} evaluation_target={} page_size={}",
            total,
            evaluation_target,
            PAGE_SIZE
        );

        /*
         * Snapshot the Email IDs before evaluation. Apply mode can change
         * mailbox membership, so the corpus must not move underneath
         * positional Email/query pagination.
         */
        let mut corpus_ids = page.take_ids();
        let mut position = PAGE_SIZE;

        while corpus_ids.len() < evaluation_target {
            let mut next_page = match throttle::with_retry("Email/query", || {
                let mut request = client.build();
                let query = request
                    .query_email()
                    .position(position as i32)
                    .limit(PAGE_SIZE);
                if let Some(mailbox_id) = &mailbox_filter_id {
                    query.filter(email::query::Filter::in_mailbox(mailbox_id));
                }
                request.send_query_email()
            }) {
                Ok(page) => page,
                Err(error) => {
                    eprintln!(
                        "resieve: Email/query failed while snapshotting position {}: {:?}",
                        position,
                        error
                    );
                    process::exit(1);
                }
            };

            let mut ids = next_page.take_ids();

            if ids.is_empty() {
                break;
            }

            corpus_ids.append(&mut ids);
            position += PAGE_SIZE;
        }

        corpus_ids.truncate(evaluation_target);

        // Positional paging under concurrent change can repeat (and so also
        // skip) an id: such a snapshot cannot prove anything is gone.
        let mut seen_ids = BTreeSet::new();
        let before_dedup = corpus_ids.len();
        corpus_ids.retain(|id| seen_ids.insert(id.clone()));
        let snapshot_consistent = corpus_ids.len() == before_dedup;
        if !snapshot_consistent {
            println!(
                "resieve: snapshot repeated {} ids (mail arrived meanwhile); no provenance cleanup this run",
                before_dedup - corpus_ids.len()
            );
        }

        (corpus_ids, total, evaluation_target, snapshot_consistent)
    };

    println!(
        "resieve: snapshotted {} Email IDs before evaluation",
        corpus_ids.len()
    );

    let header_only = sieve.headers_suffice && !config.full_messages;
    println!(
        "resieve: Email/get in batches of {}; {}",
        PAGE_SIZE,
        if header_only {
            "the active script reads only header fields: evaluating headers, no downloads"
        } else if sieve.headers_suffice {
            "full messages (RESIEVE_FULL_MESSAGES=1), downloads over one connection"
        } else {
            "full messages, downloads over one connection"
        }
    );

    for chunk in corpus_ids.chunks(PAGE_SIZE) {
        // One Email/get for the whole page instead of one per mail; with
        // the header fields when the script reads nothing else.
        let (found, batch_error) = match downloader.email_get(chunk, header_only) {
            Ok(found) => (found, None),
            Err(error) => (BTreeMap::new(), Some(error)),
        };

        // Moves of this page, applied after it with one Email/set.
        let mut moves: Vec<Move> = Vec::new();

        // Downloads stay sequential: in parallel (4 or 8 at a time) a run
        // was several times slower against Stalwart (measured 2026-10-07).
        {
            for email_id in chunk {
                stats.evaluated += 1;

                if protected_email_ids.contains(email_id) {
                    stats.protected += 1;
                    stats.seen_protected.insert(email_id.clone());
                }

                if let Some(error) = &batch_error {
                    stats.errors += 1;
                    eprintln!(
                        "resieve: Email/get failed id={} error={}",
                        email_id, error
                    );
                    continue;
                }

                let email = match found.get(email_id) {
                    Some(email) => email,
                    None => {
                        stats.errors += 1;
                        eprintln!(
                            "resieve: email disappeared id={}",
                            email_id
                        );
                        continue;
                    }
                };

                let download = if header_only {
                    email.headers.as_ref().map(|fields| {
                        Ok(script_scope::header_message(
                            fields.iter().map(|(name, value)| (name.as_str(), value.as_str())),
                        ))
                    })
                } else {
                    email
                        .blob_id
                        .as_deref()
                        .map(|blob_id| downloader.download(blob_id))
                };
                let raw_message = match download {
                    Some(Ok(raw_message)) => raw_message,
                    Some(Err(error)) => {
                        stats.errors += 1;
                        eprintln!(
                            "resieve: blob download failed id={} error={}",
                            email_id, error
                        );
                        continue;
                    }
                    None => {
                        stats.errors += 1;
                        eprintln!(
                            "resieve: nothing to evaluate (no blobId or headers) id={}",
                            email_id
                        );
                        continue;
                    }
                };

                match sieve.evaluate(&raw_message) {
                    Ok(SieveResult::Finished { placement, create }) => {
                        stats.finished += 1;
                        let current: BTreeSet<String> =
                            email.mailbox_ids.iter().cloned().collect();

                        if protected_email_ids.contains(email_id) {
                            if !placement.is_empty() {
                                stats.planned_preserve += 1;
                            }
                        } else if current.iter().any(|id| protected_folders.contains(id)) {
                            stats.in_protected_folder += 1;
                        } else if placement.is_empty() {
                            stats.no_placement += 1;
                        } else if resort && placement.iter().all(|p| p.eq_ignore_ascii_case("INBOX")) {
                            // Re-sort chute: no rule matches, the mail stays
                            // where the human put it, and the human's move
                            // is the spam verdict: Junk -> INBOX is "not spam",
                            // a drag into Junk is "spam". Recorded as keywords,
                            // so the next filter change does not undo it.
                            stats.stays_no_rule += 1;
                            let in_inbox = inbox_id.as_ref().map_or(false, |i| current.contains(i));
                            let in_junk = junk_id.as_ref().map_or(false, |j| current.contains(j));
                            let verdict = if in_junk && !email.spam {
                                Some(true)
                            } else if in_inbox && !in_junk && email.spam {
                                Some(false)
                            } else {
                                None
                            };
                            if let Some(spam) = verdict {
                                // A planned write like a move: counted, so
                                // an applied verdict completes the run.
                                stats.would_move += 1;
                                *stats
                                    .transitions
                                    .entry(if spam { "verdict: spam" } else { "verdict: not spam" }.to_string())
                                    .or_insert(0) += 1;
                                if config.apply {
                                    moves.push(Move { id: email_id.clone(), desired: current.clone(), clear_junk: false, verdict });
                                }
                            }
                        } else {
                            let mut desired = BTreeSet::new();
                            let mut unresolved = false;
                            for path in &placement {
                                match mailboxes.id_for_sieve_path(path) {
                                    Some(id) => {
                                        desired.insert(id.to_string());
                                    }
                                    // `fileinto :create`: made now, as on delivery.
                                    None if create.contains(path) => {
                                        match ensure_folder(&downloader, &mut mailboxes, path, config.apply) {
                                            Ok(id) => {
                                                desired.insert(id);
                                            }
                                            Err(error) => {
                                                eprintln!("resieve: cannot create {:?}: {}", path, error);
                                                unresolved = true;
                                            }
                                        }
                                    }
                                    // A missing folder without :create: INBOX,
                                    // as on delivery.
                                    None => match &inbox_id {
                                        Some(id) => {
                                            desired.insert(id.clone());
                                        }
                                        None => unresolved = true,
                                    },
                                }
                            }
                            // Stalwart's junk rule: spam the filter leaves only
                            // in INBOX goes to Junk (not on a re-sort: there
                            // "no rule" means "stays").
                            if !resort && email.spam && inbox_id.as_ref().map_or(false, |inbox| {
                                desired.len() == 1 && desired.contains(inbox)
                            }) {
                                if let Some(junk) = &junk_id {
                                    desired = BTreeSet::from([junk.clone()]);
                                }
                            }
                            // A re-sort keeps the mail's folders outside the
                            // chute: the human put it there too (a copy into
                            // INBOX is the same mail in two folders).
                            if resort {
                                desired.extend(current.difference(&chute).cloned());
                            }
                            // A rule that files spam elsewhere overrules the
                            // verdict: the junk flag goes.
                            let clear_junk = email.spam
                                && !junk_id.as_ref().map_or(false, |junk| desired.contains(junk));
                            if unresolved {
                                stats.unresolved_destination += 1;
                            } else if let Some((add, remove)) = plan(&current, &desired) {
                                stats.would_move += 1;
                                let label = |ids: &BTreeSet<String>| {
                                    let mut paths: Vec<String> = ids
                                        .iter()
                                        .map(|id| {
                                            mailboxes
                                                .path_for_id(id)
                                                .map(str::to_string)
                                                .unwrap_or_else(|| format!("<unknown:{}>", id))
                                        })
                                        .collect();
                                    paths.sort();
                                    if paths.is_empty() { "<none>".to_string() } else { paths.join(" + ") }
                                };
                                let after: BTreeSet<String> = current
                                    .difference(&remove)
                                    .cloned()
                                    .chain(add.iter().cloned())
                                    .collect();
                                *stats
                                    .transitions
                                    .entry(format!("{} -> {}", label(&current), label(&after)))
                                    .or_insert(0) += 1;
                                if config.apply {
                                    moves.push(Move { id: email_id.clone(), desired, clear_junk, verdict: None });
                                }
                            } else {
                                stats.already_correct += 1;
                            }
                        }
                    }
                    Ok(SieveResult::Pending) => {
                        stats.pending += 1;
                    }
                    Err(error) => {
                        stats.errors += 1;
                        eprintln!(
                            "resieve: Sieve runtime error id={} error={}",
                            email_id,
                            error
                        );
                    }
                }

                if stats.evaluated % 1000 == 0 || stats.evaluated == total {
                    let elapsed = started.elapsed().as_secs_f64();
                    let rate = if elapsed > 0.0 {
                        stats.evaluated as f64 / elapsed
                    } else {
                        0.0
                    };

                    println!(
                        "resieve: progress {}/{} ({:.1} msg/s)",
                        stats.evaluated,
                        total,
                        rate
                    );
                }
            }
        }

        apply_moves(&downloader, &moves, &rules, &mut stats);
    }

    // A provenance entry is removed only when Stalwart itself says the mail
    // is gone, and only by a complete, consistent, error-free --apply run (a
    // dry run changes nothing, provenance included).
    let mut cleanup_removed = 0;
    if config.apply
        && !resort
        && config.limit.is_none()
        && config.mailbox_filter.is_none()
        && snapshot_consistent
        && stats.evaluated == total
        && stats.errors == 0
        && stats.pending == 0
    {
        let unseen: Vec<String> = protected_email_ids
            .difference(&stats.seen_protected)
            .cloned()
            .collect();
        let mut gone = BTreeSet::new();
        let mut confirmed = true;
        for chunk in unseen.chunks(PAGE_SIZE) {
            match downloader.membership(chunk) {
                Ok(m) => gone.extend(m.not_found),
                Err(error) => {
                    eprintln!("resieve: provenance cleanup skipped: {error}");
                    confirmed = false;
                    break;
                }
            }
        }
        if confirmed && !gone.is_empty() {
            cleanup_removed = provenance::remove(&config.provenance_path, &config.account, &gone);
        }
        println!(
            "resieve: provenance cleanup removed {} entries of mail Stalwart reports gone",
            cleanup_removed
        );
    } else {
        println!("resieve: provenance cleanup skipped (dry run, scoped, inconsistent or errored run)");
    }

    let elapsed = started.elapsed();
    let seconds = elapsed.as_secs_f64();

    println!();
    if config.apply {
        println!("===== RESIEVE APPLY SUMMARY =====");
    } else {
        println!("===== RESIEVE DRY-RUN SUMMARY =====");
    }
    println!("messages expected:  {}", total);
    println!("evaluation target:  {}", evaluation_target);
    println!("messages evaluated: {}", stats.evaluated);
    println!("finished:           {}", stats.finished);
    println!("pending:            {}", stats.pending);
    println!("errors:             {}", stats.errors);
    println!("protected:          {}", stats.protected);
    println!("planned preserve:   {}", stats.planned_preserve);
    println!("already correct:    {}", stats.already_correct);
    println!("would move:         {}", stats.would_move);
    println!("applied moves:      {}", stats.applied_moves);
    println!("mutation errors:    {}", stats.mutation_errors);
    println!("unresolved dest:    {}", stats.unresolved_destination);
    println!("in protected fold.: {}", stats.in_protected_folder);
    println!("no placement:       {}", stats.no_placement);
    if resort {
        println!("stays (no rule):    {}", stats.stays_no_rule);
    }
    println!("skipped at apply:   {}", stats.skipped_at_apply);
    println!("provenance cleanup: {} removed", cleanup_removed);
    println!();

    println!("transitions:");

    if stats.transitions.is_empty() {
        println!("  (none)");
    } else {
        for (transition, count) in &stats.transitions {
            println!("  {:<48} {}", transition, count);
        }
    }

    println!();
    println!("actions:");

    if sieve.actions().is_empty() {
        println!("  (none)");
    } else {
        for (action, count) in sieve.actions() {
            println!("  {:<32} {}", action, count);
        }
    }

    println!();
    println!("elapsed: {:.3}s", seconds);

    if seconds > 0.0 {
        println!(
            "throughput: {:.1} messages/sec",
            stats.evaluated as f64 / seconds
        );
    }

    let run_ok = stats.run_ok(
        evaluation_target,
        config.apply,
    );

    if !run_ok {
        eprintln!(
            "resieve: ERROR: run invariants failed: \
evaluated={}/{} pending={} errors={} unresolved={} would_move={} applied_moves={}",
            stats.evaluated,
            evaluation_target,
            stats.pending,
            stats.errors,
            stats.unresolved_destination,
            stats.would_move,
            stats.applied_moves
        );
        process::exit(1);
    }

    let scope = if resort {
        "re-sort"
    } else if config.limit.is_some() || config.mailbox_filter.is_some() {
        "scoped"
    } else {
        "full-corpus"
    };

    let mode = if config.apply {
        "apply"
    } else {
        "dry-run"
    };

    println!("resieve {} {}: OK", scope, mode);
}

#[cfg(test)]
mod tests {
    use super::{plan, RunStats};
    use std::collections::BTreeSet;

    fn set(items: &[&str]) -> BTreeSet<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    // Folder ids: I = INBOX, B = Bank, R = Receipts, K = Keep.
    #[test]
    fn plain_fileinto_moves_out_of_inbox() {
        assert_eq!(plan(&set(&["I"]), &set(&["B"])), Some((set(&["B"]), set(&["I"]))));
    }

    #[test]
    fn already_there_is_nothing() {
        assert_eq!(plan(&set(&["B"]), &set(&["B"])), None);
    }

    #[test]
    fn copy_keeps_inbox() {
        assert_eq!(plan(&set(&["I"]), &set(&["I", "R"])), Some((set(&["R"]), set(&[]))));
    }

    #[test]
    fn unprotected_mail_ends_up_exactly_where_the_filter_puts_it() {
        assert_eq!(plan(&set(&["I", "K"]), &set(&["B"])), Some((set(&["B"]), set(&["I", "K"]))));
        assert_eq!(plan(&set(&["K"]), &set(&["I"])), Some((set(&["I"]), set(&["K"]))));
    }

    #[test]
    fn a_filter_copy_is_removed_when_the_filter_changes() {
        assert_eq!(plan(&set(&["I", "R"]), &set(&["I"])), Some((set(&[]), set(&["R"]))));
    }

    #[test]
    fn apply_counts_skips_as_done() {
        let mut stats = finished(10, 3, 2);
        stats.skipped_at_apply = 1;
        assert!(stats.run_ok(10, true));
    }

    fn finished(evaluated: usize, would_move: usize, applied: usize) -> RunStats {
        let mut stats = RunStats::new();
        stats.evaluated = evaluated;
        stats.would_move = would_move;
        stats.applied_moves = applied;
        stats
    }

    #[test]
    fn dry_run_complete_is_ok() {
        assert!(finished(10, 3, 0).run_ok(10, false));
    }

    #[test]
    fn short_evaluation_is_not_ok() {
        assert!(!finished(9, 0, 0).run_ok(10, false));
    }

    #[test]
    fn apply_needs_every_planned_move() {
        assert!(finished(10, 3, 3).run_ok(10, true));
        assert!(!finished(10, 3, 2).run_ok(10, true));
    }

    #[test]
    fn errors_pending_or_unresolved_are_not_ok() {
        for field in 0..3 {
            let mut stats = finished(10, 0, 0);
            match field {
                0 => stats.errors = 1,
                1 => stats.pending = 1,
                _ => stats.unresolved_destination = 1,
            }
            assert!(!stats.run_ok(10, false));
        }
    }
}
