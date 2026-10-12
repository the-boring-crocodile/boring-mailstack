# Browser checks

Headless Chromium (Playwright, pinned base image) against a running demo.

```bash
docker build -t boring-mailstack-browser tests/browser
docker run --rm --network <demo project>_webmail \
    -v "$PWD/tests/browser:/t:ro" -v "<demo dir>/seed-accounts.json:/a.json:ro" -v /tmp:/out \
    --entrypoint python3 boring-mailstack-browser \
    /t/ics_invitation.py otter 1 "Management/Calendar (not attended)" /out/ics.jpg
```

`ics_invitation.py`: Kolab's invitation box (Accept, Maybe, Decline, ...)
with Roundav active; the .ics attachment menu lists both "Save to cloud" and
"Save to calendar". Observed 2026-10-07: passes, identical with Roundav
switched off except for the "Save to cloud" entry (Roundav issue #6 does not
reproduce with Roundav 3.0.1, Kolab df6f30f, Roundcube 1.7.4).

The acceptance test (`tests/demo/run.sh`, step 4) runs `ics_invitation.py`,
`inject_invite.py` with `ics_accept.py`, `itip_save_sent_pref.py` and
`darkmail.py`. `no_cloud_manual.py` is a manual lab check, not part of it
(how to run it is in its docstring).

`screenshot.py` is not a check: it makes the README screenshot
(`docs/screenshot.png`) from a freshly seeded demo; how to run it is in its
docstring.
