use jmap_client::client::Client;
use serde_json::{json, Value};
use std::{collections::BTreeMap, time::Duration};

use crate::throttle;

/// What resieve needs of one mail.
pub struct Fetched {
    pub blob_id: Option<String>,
    pub mailbox_ids: Vec<String>,
    /// Top-level header fields (name, raw value), when asked for.
    pub headers: Option<Vec<(String, String)>>,
    /// Spam as Stalwart sees it: the `$junk` keyword or a spam verdict in
    /// X-Spam-Score, unless the user said "not spam" (`$notjunk`).
    pub spam: bool,
}

/// Outcome of one Email/set.
pub enum SetError {
    /// ifInState no longer matches: something changed in the account.
    StateMismatch,
    Other(String),
}

pub struct SetResult {
    pub updated: std::collections::BTreeSet<String>,
    pub not_updated: BTreeMap<String, String>,
}

/// Mailbox membership of some mails at one Email state (for a write with
/// ifInState), and which of them no longer exist.
pub struct Membership {
    pub state: String,
    pub mailbox_ids: BTreeMap<String, Vec<String>>,
    pub not_found: Vec<String>,
}

/// Blob downloads and the JMAP calls jmap-client 0.4.2 cannot make, over
/// one long-lived HTTP client: jmap-client builds a new HTTP client (new
/// connection, TLS handshake, runtime thread) for every download; with one
/// download per mail that dominated a run (measured 2026-10-07 on a 49k-mail
/// fixture). Same URL, credentials and certificate policy as the JMAP client
/// (Stalwart on the private Docker network; DECISIONS.md, TLS inside the
/// stack). Every request waits and tries again while Stalwart answers 429.
pub struct Downloader {
    http: reqwest::blocking::Client,
    api_url: String,
    template: String,
    account_id: String,
    username: String,
    password: String,
}

impl Downloader {
    pub fn new(client: &Client, username: &str, password: &str) -> Result<Self, String> {
        let http = reqwest::blocking::Client::builder()
            .danger_accept_invalid_certs(true)
            .timeout(Duration::from_secs(120))
            .pool_max_idle_per_host(64)
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|error| format!("HTTP client: {error}"))?;

        Ok(Self {
            http,
            api_url: client.session().api_url().to_string(),
            template: client.session().download_url().to_string(),
            account_id: client.default_account_id().to_string(),
            username: username.to_string(),
            password: password.to_string(),
        })
    }

    /// Sends the request `build` makes, again after a pause while Stalwart
    /// answers 429; other answers are returned as they are.
    fn send(
        &self,
        what: &str,
        build: impl Fn() -> reqwest::blocking::RequestBuilder,
    ) -> Result<reqwest::blocking::Response, String> {
        let mut attempt = 0;
        loop {
            let response = build()
                .basic_auth(&self.username, Some(&self.password))
                .send()
                .map_err(|error| format!("{error}"))?;
            if response.status() == reqwest::StatusCode::TOO_MANY_REQUESTS && attempt < throttle::RETRIES {
                throttle::pause(what, attempt);
                attempt += 1;
                continue;
            }
            if !response.status().is_success() {
                return Err(format!("HTTP {}", response.status()));
            }
            return Ok(response);
        }
    }

    /// One JMAP method call; the whole response.
    fn call(&self, method: &str, args: Value) -> Result<Value, String> {
        let body = json!({
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
            "methodCalls": [[method, args, "0"]],
        });
        self.send(method, || self.http.post(&self.api_url).json(&body))?
            .json()
            .map_err(|error| format!("{error}"))
    }

    /// One Email/get for a page of ids (jmap-client 0.4.2 has no
    /// "headers" property, so the request is made here). Mails the server
    /// does not return are missing from the map.
    pub fn email_get(
        &self,
        ids: &[String],
        headers: bool,
    ) -> Result<BTreeMap<String, Fetched>, String> {
        let mut properties = vec!["id", "blobId", "mailboxIds", "keywords", "header:X-Spam-Score:asText"];
        if headers {
            properties.push("headers");
        }
        let value = self.call("Email/get", json!({
            "accountId": self.account_id, "ids": ids, "properties": properties,
        }))?;
        parse_email_get(&value)
    }

    /// Email/get of mailboxIds only, with the Email state and notFound.
    pub fn membership(&self, ids: &[String]) -> Result<Membership, String> {
        let value = self.call("Email/get", json!({
            "accountId": self.account_id, "ids": ids, "properties": ["id", "mailboxIds"],
        }))?;
        parse_membership(&value)
    }

    /// One Email/set of patches, with ifInState when given.
    pub fn email_set(
        &self,
        updates: &serde_json::Map<String, Value>,
        if_in_state: Option<&str>,
    ) -> Result<SetResult, SetError> {
        let mut args = json!({"accountId": self.account_id, "update": updates});
        if let Some(state) = if_in_state {
            args["ifInState"] = json!(state);
        }
        let value = self.call("Email/set", args).map_err(SetError::Other)?;
        parse_email_set(&value)
    }

    /// Creates a folder (Mailbox/set), subscribed so webmail shows it.
    pub fn mailbox_create(&self, name: &str, parent_id: Option<&str>) -> Result<String, String> {
        let value = self.call("Mailbox/set", json!({"accountId": self.account_id, "create": {"n": {
            "name": name, "parentId": parent_id, "isSubscribed": true}}}))?;
        value["methodResponses"][0][1]["created"]["n"]["id"]
            .as_str()
            .map(str::to_string)
            .ok_or_else(|| format!("Mailbox/set failed: {}", value["methodResponses"][0]))
    }

    pub fn url(&self, blob_id: &str) -> String {
        fill(&self.template, &self.account_id, blob_id)
    }

    pub fn download(&self, blob_id: &str) -> Result<Vec<u8>, String> {
        self.send("download", || self.http.get(self.url(blob_id)))?
            .bytes()
            .map(|bytes| bytes.to_vec())
            .map_err(|error| format!("{error}"))
    }
}

fn parse_email_get(value: &Value) -> Result<BTreeMap<String, Fetched>, String> {
    let call = &value["methodResponses"][0];
    if call[0] != "Email/get" {
        return Err(format!("unexpected response: {}", call));
    }
    let mut out = BTreeMap::new();
    for item in call[1]["list"].as_array().into_iter().flatten() {
        let Some(id) = item["id"].as_str() else { continue };
        let mailbox_ids = item["mailboxIds"]
            .as_object()
            .map(|m| m.iter().filter(|(_, v)| v.as_bool() == Some(true)).map(|(k, _)| k.clone()).collect())
            .unwrap_or_default();
        let headers = item["headers"].as_array().map(|fields| {
            fields
                .iter()
                .filter_map(|f| Some((f["name"].as_str()?.to_string(), f["value"].as_str()?.to_string())))
                .collect()
        });
        let keywords: Vec<String> = item["keywords"]
            .as_object()
            .map(|k| k.iter().filter(|(_, v)| v.as_bool() == Some(true)).map(|(k, _)| k.to_ascii_lowercase()).collect())
            .unwrap_or_default();
        let score = item["header:X-Spam-Score:asText"].as_str().unwrap_or("").trim().to_ascii_lowercase();
        let spam = !keywords.iter().any(|k| k == "$notjunk")
            && (keywords.iter().any(|k| k == "$junk") || score.starts_with("spam"));
        out.insert(
            id.to_string(),
            Fetched {
                blob_id: item["blobId"].as_str().map(str::to_string),
                mailbox_ids,
                headers,
                spam,
            },
        );
    }
    Ok(out)
}

fn parse_email_set(value: &Value) -> Result<SetResult, SetError> {
    let call = &value["methodResponses"][0];
    if call[0] == "error" {
        return Err(if call[1]["type"] == "stateMismatch" {
            SetError::StateMismatch
        } else {
            SetError::Other(format!("{}", call[1]))
        });
    }
    if call[0] != "Email/set" {
        return Err(SetError::Other(format!("unexpected response: {}", call)));
    }
    let updated = call[1]["updated"]
        .as_object()
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default();
    let not_updated = call[1]["notUpdated"]
        .as_object()
        .map(|m| m.iter().map(|(k, v)| (k.clone(), v.to_string())).collect())
        .unwrap_or_default();
    Ok(SetResult { updated, not_updated })
}

fn parse_membership(value: &Value) -> Result<Membership, String> {
    let state = value["methodResponses"][0][1]["state"]
        .as_str()
        .ok_or_else(|| format!("unexpected response: {}", value["methodResponses"][0]))?
        .to_string();
    let found = parse_email_get(value)?;
    let not_found = value["methodResponses"][0][1]["notFound"]
        .as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    Ok(Membership {
        state,
        mailbox_ids: found.into_iter().map(|(id, f)| (id, f.mailbox_ids)).collect(),
        not_found,
    })
}

/// The session's downloadUrl template (RFC 8620, 2) with its variables set.
fn fill(template: &str, account_id: &str, blob_id: &str) -> String {
    template
        .replace("{accountId}", account_id)
        .replace("{blobId}", blob_id)
        .replace("{name}", "message.eml")
        .replace("{type}", "message%2Frfc822")
}

#[cfg(test)]
mod tests {
    use super::fill;

    #[test]
    fn email_get_response() {
        let value = serde_json::json!({"methodResponses": [["Email/get", {"list": [
            {"id": "a", "blobId": "ba", "mailboxIds": {"m1": true},
             "headers": [{"name": "Subject", "value": " hi"}]},
            {"id": "b", "blobId": "bb", "mailboxIds": {"m1": true, "m2": true}}
        ], "notFound": ["c"]}, "0"]]});
        let got = super::parse_email_get(&value).unwrap();
        assert_eq!(got.len(), 2);
        assert_eq!(got["a"].headers.as_ref().unwrap()[0], ("Subject".into(), " hi".into()));
        assert_eq!(got["b"].mailbox_ids.len(), 2);
        assert!(got["b"].headers.is_none());
        assert!(super::parse_email_get(&serde_json::json!({"methodResponses": [["error", {"type": "x"}, "0"]]})).is_err());
    }

    #[test]
    fn spam_from_keywords_and_score() {
        let value = serde_json::json!({"methodResponses": [["Email/get", {"list": [
            {"id": "k", "mailboxIds": {}, "keywords": {"$Junk": true}},
            {"id": "s", "mailboxIds": {}, "header:X-Spam-Score:asText": " spam, score=8.7"},
            {"id": "n", "mailboxIds": {}, "keywords": {"$junk": true, "$NotJunk": true}},
            {"id": "h", "mailboxIds": {}, "header:X-Spam-Score:asText": "ham, score=0.1"}
        ]}, "0"]]});
        let got = super::parse_email_get(&value).unwrap();
        assert!(got["k"].spam && got["s"].spam);
        assert!(!got["n"].spam && !got["h"].spam);
    }

    #[test]
    fn email_set_response() {
        let ok = serde_json::json!({"methodResponses": [["Email/set",
            {"updated": {"a": null}, "notUpdated": {"b": {"type": "notFound"}}}, "0"]]});
        let got = super::parse_email_set(&ok).ok().unwrap();
        assert!(got.updated.contains("a") && got.not_updated.contains_key("b"));
        let mismatch = serde_json::json!({"methodResponses": [["error", {"type": "stateMismatch"}, "0"]]});
        assert!(matches!(super::parse_email_set(&mismatch), Err(super::SetError::StateMismatch)));
    }

    #[test]
    fn membership_response() {
        let value = serde_json::json!({"methodResponses": [["Email/get", {"state": "s7", "list": [
            {"id": "a", "mailboxIds": {"m1": true}}], "notFound": ["c"]}, "0"]]});
        let got = super::parse_membership(&value).unwrap();
        assert_eq!(got.state, "s7");
        assert_eq!(got.mailbox_ids["a"], vec!["m1".to_string()]);
        assert_eq!(got.not_found, vec!["c".to_string()]);
    }

    #[test]
    fn template_variables() {
        assert_eq!(
            fill(
                "https://stalwart.mailstack.local/jmap/download/{accountId}/{blobId}/{name}?accept={type}",
                "c",
                "bx1"
            ),
            "https://stalwart.mailstack.local/jmap/download/c/bx1/message.eml?accept=message%2Frfc822"
        );
    }
}
