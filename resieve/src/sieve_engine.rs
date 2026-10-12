use jmap_client::{
    client::Client,
    sieve as jmap_sieve,
};
use sieve::{
    Arena, Compiler, Context, Handler, Reply, Runtime,
    Sieve, SieveAction, Status,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    process,
};

// Fetches and evaluates Stalwart's active Sieve program unchanged.
// Evaluation itself has no external side effects; the caller decides
// what, if anything, a recorded result means for historical mail.
pub struct SieveEngine {
    /// The script reads only header fields (script_scope).
    pub headers_suffice: bool,
    runtime: Runtime,
    compiled: Sieve<'static>,
    handler: SieveHandler,
}

impl SieveEngine {
    pub fn load(client: &Client) -> Self {
        let mut query = client
            .sieve_script_query(
                jmap_sieve::query::Filter::is_active(true).into(),
                None::<Vec<_>>,
            )
            .expect("SieveScript/query failed");

        let sieve_ids = query.take_ids();

        if sieve_ids.len() != 1 {
            eprintln!(
                "expected exactly one active Sieve script, found {}",
                sieve_ids.len()
            );
            process::exit(1);
        }

        let sieve_id = &sieve_ids[0];

        let script = client
            .sieve_script_get(
                sieve_id,
                [jmap_sieve::Property::BlobId].into(),
            )
            .expect("SieveScript/get failed")
            .expect("active Sieve script disappeared");

        let blob_id = script
            .blob_id()
            .expect("active Sieve script has no blobId");

        let bytes = client
            .download(blob_id)
            .expect("active Sieve blob download failed");

        println!(
            "resieve: active sieve id={} bytes={}",
            sieve_id,
            bytes.len()
        );

        Self::from_bytes(&bytes).unwrap_or_else(|error| {
            eprintln!("Sieve compilation failed: {error}");
            process::exit(1);
        })
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Self, String> {
        let compiled = Compiler::new()
            .compile(bytes)
            .map_err(|error| format!("{error:?}"))?;

        println!("resieve: active Sieve compiled successfully");

        let headers_suffice = std::str::from_utf8(bytes)
            .map(crate::script_scope::headers_suffice)
            .unwrap_or(false);

        Ok(Self {
            headers_suffice,
            runtime: Runtime::new(),
            compiled,
            handler: SieveHandler::new(),
        })
    }

    pub fn evaluate<'a>(
        &'a mut self,
        raw_message: &[u8],
    ) -> Result<SieveResult<'a>, String> {
        self.handler.begin_message();

        let mut arena = Arena::new();
        let mut instance = self.runtime.filter(
            raw_message,
            &self.compiled,
            &mut arena,
        );

        match instance.run(&mut self.handler) {
            Ok(Status::Finished) => Ok(SieveResult::Finished {
                placement: self.handler.placement.iter().map(String::as_str).collect(),
                create: self.handler.create.iter().map(String::as_str).collect(),
            }),
            Ok(Status::Pending) => Ok(SieveResult::Pending),
            Err(error) => Err(format!("{error:?}")),
        }
    }

    pub fn actions(&self) -> &BTreeMap<String, usize> {
        &self.handler.actions
    }
}

pub enum SieveResult<'a> {
    /// Where delivery would have put the message: every `fileinto` folder,
    /// plus INBOX for an explicit or implicit keep (`:copy` keeps it).
    /// Empty when the script disposes of the message otherwise (discard,
    /// reject, redirect without :copy): resieve then leaves it where it is.
    Finished {
        placement: Vec<&'a str>,
        /// Folders named with `fileinto :create`: made when missing. Any
        /// other missing folder means INBOX, as on delivery.
        create: Vec<&'a str>,
    },
    Pending,
}

struct SieveHandler {
    actions: BTreeMap<String, usize>,
    placement: BTreeSet<String>,
    create: BTreeSet<String>,
}

impl SieveHandler {
    fn new() -> Self {
        Self {
            actions: BTreeMap::new(),
            placement: BTreeSet::new(),
            create: BTreeSet::new(),
        }
    }

    fn record(&mut self, name: String) {
        *self.actions.entry(name).or_insert(0) += 1;
    }

    fn begin_message(&mut self) {
        self.placement.clear();
        self.create.clear();
    }
}

impl<'x> Handler<'x> for SieveHandler {
    fn action(
        &mut self,
        _: &Context<'x>,
        action: SieveAction<'_>,
    ) -> Reply<()> {
        let name = match action {
            SieveAction::FileInto { folder, create, .. } => {
                self.placement.insert(folder.to_string());
                if create {
                    self.create.insert(folder.to_string());
                }
                format!("FileInto {:?}", folder)
            }
            // sieve-rs reports the keep that survives the script (implicit
            // or explicit; `fileinto :copy` does not cancel it) as Keep.
            SieveAction::Keep { .. } => {
                self.placement.insert("INBOX".to_string());
                "Keep".to_string()
            }
            other => {
                let debug = format!("{other:?}");
                debug
                    .split(|c| c == ' ' || c == '{' || c == '(')
                    .next()
                    .unwrap_or("Other")
                    .to_string()
            }
        };

        self.record(name);

        // Sieve evaluation itself has no external side effects.
        // Resieve interprets the recorded result separately.
        Reply::Ready(())
    }
}


#[cfg(test)]
mod tests {
    use super::{SieveEngine, SieveResult};

    fn placement(script: &str) -> Vec<String> {
        let mut engine = SieveEngine::from_bytes(script.as_bytes()).unwrap();
        let mail = b"From: a@bank.example\r\nTo: b@x.test\r\nSubject: invoice\r\n\r\nbody\r\n";
        match engine.evaluate(mail).unwrap() {
            SieveResult::Finished { placement, .. } => placement.iter().map(|s| s.to_string()).collect(),
            SieveResult::Pending => panic!("pending"),
        }
    }

    #[test]
    fn engine_keep_semantics() {
        let req = "require [\"fileinto\", \"copy\"];\n";
        assert_eq!(placement(""), vec!["INBOX"]);
        assert_eq!(placement(&format!("{req}fileinto \"Bank\";")), vec!["Bank"]);
        assert_eq!(placement(&format!("{req}fileinto :copy \"R\";")), vec!["INBOX", "R"]);
        assert_eq!(placement(&format!("{req}fileinto \"Bank\"; keep;")), vec!["Bank", "INBOX"]);
        assert!(placement("discard;").is_empty());
        assert!(placement("redirect \"c@x.test\";").is_empty());
    }
}
