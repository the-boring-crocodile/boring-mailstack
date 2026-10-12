use std::{thread, time::Duration};

// Stalwart limits requests per authenticated account and answers HTTP 429
// above it. A full run over a large mailbox reached Stalwart's default of
// 60,000 per minute (one download per mail; observed 2026-10-07 on a
// 49k-mail fixture); stalwart-provision now sets 600,000. resieve still
// waits and tries again instead of counting a refused request as an error.
pub const RETRIES: u32 = 12;

/// Wait before retry number `attempt` (0-based): 1, 2, 4, 8, 16, then 30 s;
/// twelve retries wait about four minutes in all, several rate windows.
pub fn backoff(attempt: u32) -> Duration {
    Duration::from_secs((1u64 << attempt.min(5)).min(30))
}

pub fn is_rate_limited(error: &jmap_client::Error) -> bool {
    matches!(error, jmap_client::Error::Problem(problem) if problem.status() == Some(429))
}

/// Runs `call`, and again after a pause while Stalwart answers 429.
pub fn with_retry<T>(
    what: &str,
    mut call: impl FnMut() -> jmap_client::Result<T>,
) -> jmap_client::Result<T> {
    let mut attempt = 0;
    loop {
        match call() {
            Err(error) if is_rate_limited(&error) && attempt < RETRIES => {
                pause(what, attempt);
                attempt += 1;
            }
            other => return other,
        }
    }
}

pub fn pause(what: &str, attempt: u32) {
    let wait = backoff(attempt);
    eprintln!(
        "resieve: {what}: rate limited by Stalwart, waiting {} s",
        wait.as_secs()
    );
    thread::sleep(wait);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backoff_grows_and_caps() {
        let waits: Vec<u64> = (0..8).map(|a| backoff(a).as_secs()).collect();
        assert_eq!(waits, vec![1, 2, 4, 8, 16, 30, 30, 30]);
        let total: u64 = (0..RETRIES).map(|a| backoff(a).as_secs()).sum();
        assert!(total > 120, "{total}");
    }

    #[test]
    fn other_errors_are_not_retried() {
        let mut calls = 0;
        let result: jmap_client::Result<u32> = with_retry("test", || {
            calls += 1;
            Err(jmap_client::Error::Internal("not a 429".into()))
        });
        assert!(result.is_err());
        assert_eq!(calls, 1, "other errors are not retried");
    }
}
