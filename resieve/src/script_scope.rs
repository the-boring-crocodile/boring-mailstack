// Does a Sieve script look only at a message's top-level header fields?
// Then resieve can evaluate it on the headers alone (fetched in batches
// with Email/get) instead of downloading every message.
//
// Conservative on purpose: every extension the script requires must be on
// ALLOWED (extensions that read nothing beyond header fields, or only act),
// and the script must not use a test that reads more (FORBIDDEN, e.g. the
// core `size` test, which needs no `require`). Anything unknown: full
// messages, as before.

const ALLOWED: &[&str] = &[
    "fileinto",
    "special-use",
    "mailbox",
    "imap4flags",
    "copy",
    "variables",
    "relational",
    "regex",
    "subaddress",
    "date",
    "index",
    "encoded-character",
    "comparator-i;ascii-numeric",
    "comparator-i;octet",
    "comparator-i;ascii-casemap",
    "reject",
    "ereject",
    "vacation",
    "vacation-seconds",
];

const FORBIDDEN: &[&str] = &[
    "size",
    "body",
    "envelope",
    "spamtest",
    "virustest",
    "foreverypart",
    "extracttext",
    "include",
    "duplicate",
    "environment",
    ":mime",
    ":anychild",
];

#[derive(Debug, PartialEq)]
enum Token {
    Word(String),
    Text(String),
    Other(char),
}

fn tokens(script: &str) -> Vec<Token> {
    let chars: Vec<char> = script.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == '#' {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
        } else if c == '/' && chars.get(i + 1) == Some(&'*') {
            i += 2;
            while i + 1 < chars.len() && !(chars[i] == '*' && chars[i + 1] == '/') {
                i += 1;
            }
            i += 2;
        } else if c == '"' {
            let mut text = String::new();
            i += 1;
            while i < chars.len() && chars[i] != '"' {
                if chars[i] == '\\' && i + 1 < chars.len() {
                    i += 1;
                }
                text.push(chars[i]);
                i += 1;
            }
            i += 1;
            out.push(Token::Text(text));
        } else if c.is_ascii_alphabetic() || c == '_' || c == ':' {
            let start = i;
            i += 1;
            while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            let word: String = chars[start..i].iter().collect::<String>().to_ascii_lowercase();
            if word == "text:" || (word == "text" && chars.get(i) == Some(&':')) {
                // Multi-line string: up to a line holding only ".".
                let mut text = String::new();
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
                i += 1;
                loop {
                    let line_start = i;
                    while i < chars.len() && chars[i] != '\n' {
                        i += 1;
                    }
                    let line: String = chars[line_start..i].iter().collect();
                    i += 1;
                    if line.trim_end_matches('\r') == "." || i >= chars.len() {
                        break;
                    }
                    text.push_str(&line);
                    text.push('\n');
                }
                out.push(Token::Text(text));
            } else {
                out.push(Token::Word(word));
            }
        } else {
            if !c.is_whitespace() {
                out.push(Token::Other(c));
            }
            i += 1;
        }
    }
    out
}

/// True if the script reads nothing but top-level header fields.
pub fn headers_suffice(script: &str) -> bool {
    let tokens = tokens(script);
    let mut requires = Vec::new();
    let mut i = 0;
    while i < tokens.len() {
        if tokens[i] == Token::Word("require".into()) {
            i += 1;
            while i < tokens.len() && tokens[i] != Token::Other(';') {
                if let Token::Text(name) = &tokens[i] {
                    requires.push(name.to_ascii_lowercase());
                }
                i += 1;
            }
        }
        i += 1;
    }
    let words_ok = !tokens
        .iter()
        .any(|t| matches!(t, Token::Word(w) if FORBIDDEN.contains(&w.as_str())));
    let requires_ok = requires.iter().all(|r| ALLOWED.contains(&r.as_str()));
    words_ok && requires_ok
}

/// A message made of the given header fields and an empty body, as the
/// header-only evaluation sees it. JMAP's raw header value is everything
/// after the colon, so "name:value" restores the field.
pub fn header_message<'a>(fields: impl IntoIterator<Item = (&'a str, &'a str)>) -> Vec<u8> {
    let mut out = Vec::new();
    for (name, value) in fields {
        out.extend_from_slice(name.as_bytes());
        out.push(b':');
        out.extend_from_slice(value.as_bytes());
        if !value.ends_with('\n') {
            out.extend_from_slice(b"\r\n");
        }
    }
    out.extend_from_slice(b"\r\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROUNDCUBE_LIKE: &str = r#"require ["fileinto","special-use"];
# rule:[spam]
if anyof (header :contains "x-spam-flag" "YES", header :contains "subject" "size")
{
	fileinto :specialuse "\\Junk" "Junk Mail";
	stop;
}
/* a "body" mention in a comment */
if address :is "from" "x@example.org" { fileinto "INBOX"; }
"#;

    #[test]
    fn header_tests_suffice() {
        assert!(headers_suffice(ROUNDCUBE_LIKE));
    }

    #[test]
    fn size_test_needs_the_message() {
        assert!(!headers_suffice(
            "require \"fileinto\"; if size :over 1M { fileinto \"Big\"; }"
        ));
    }

    #[test]
    fn body_extension_needs_the_message() {
        assert!(!headers_suffice(
            "require [\"body\",\"fileinto\"]; if body :contains \"x\" { fileinto \"X\"; }"
        ));
    }

    #[test]
    fn unknown_extension_needs_the_message() {
        assert!(!headers_suffice(
            "require [\"fileinto\",\"vnd.stalwart.expressions\"]; keep;"
        ));
    }

    #[test]
    fn mime_tag_needs_the_message() {
        assert!(!headers_suffice(
            "require [\"fileinto\"]; if header :mime :anychild \"content-type\" \"x\" { keep; }"
        ));
    }

    #[test]
    fn words_in_strings_and_text_blocks_do_not_count() {
        let script = "require \"vacation\";\nvacation text:\nsize matters, body too\n.\n;";
        assert!(headers_suffice(script));
    }

    #[test]
    fn header_message_restores_fields() {
        let msg = header_message([("Subject", " hello"), ("X-Long", " a\r\n b")]);
        assert_eq!(msg, b"Subject: hello\r\nX-Long: a\r\n b\r\n\r\n".to_vec());
    }
}
