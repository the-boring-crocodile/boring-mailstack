# resieve with a real mailbox: fixture and benchmark

For performance work on `resieve` against a real mailbox instead of the demo
story. A real mailbox is private: keep the export and the fixture outside
the repository, mode 0700, and delete them when done.

1. **Export one account** from a running stack (`state.py export`: raw mail,
   flags, arrival dates, folders and Sieve scripts; counts on stdout). It
   runs in a container on the stack's mail network and reads the account's
   login from a JSON file `{"ACCOUNT": {"address": …, "password": …}}`:

   ```bash
   docker run --rm --network PROJECT_mail-internal \
       -v "$PWD/tests:/tests:ro" -v /path/to/login.json:/a.json:ro -v /path/to/export:/out \
       -e DEMO_ACCOUNTS=/a.json --entrypoint python3 boring-mailstack-init:VERSION \
       /tests/resieve/state.py export ACCOUNT /out
   ```

2. **A demo to hold it**, kept running:

   ```bash
   DEMO_PROJECT=boring-mailstack-resieve DEMO_RELEASE=resieve tools/demo --dir FIXTURE up --port 18790
   ```

3. **Load it into one demo account** (here croc; the story mail is removed first):

   ```bash
   docker run --rm --network boring-mailstack-resieve_mail-internal \
       -v "$PWD/tests:/tests:ro" -v FIXTURE/seed-accounts.json:/a.json:ro \
       -v /path/to/export:/x:ro -e DEMO_ACCOUNTS=/a.json \
       --entrypoint python3 boring-mailstack-init:resieve \
       /tests/resieve/fixture.py load croc /x --empty-first
   ```

4. **Run resieve, timed:** `tests/resieve/bench FIXTURE croc` (dry-run;
   `--limit N`, `--mailbox PATH`, `--apply` as in `tools/resieve`;
   `--full-messages` to download whole messages even for a header-only
   script).

5. **Repeatable apply runs:** `tests/resieve/snapshot save|restore FIXTURE SNAPSHOT_DIR`.

Results on 2026-10-07/08 (a real mailbox of 48,987 mails, a Roundcube
filter with header tests):

| resieve | dry run |
|---|---|
| before (one Email/get and one new connection per mail) | 222 s |
| Email/get per 500 | 96 s |
| + downloads over one kept-open connection | 37 s |
| header-only (filter reads only header fields) | 7 s |

Every run: the same counts, transitions and actions as the first.

Run one heavy job at a time on a rootless daemon with a per-user process
limit (a Rust build beside two test suites once took one down).

The fixture's `resieve-watch` container is better stopped: it would apply
the filter by itself after every `snapshot restore`.
