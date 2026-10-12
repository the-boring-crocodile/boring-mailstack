# Contributing

boring-mailstack is maintained for its own use and shared. Issues and
small changes are welcome; answers come when there is time, and fixes
come with the next release. Security problems: SECURITY.md, not an issue.

**Reporting a bug:** the issue template asks for the release, what you did,
what happened, and the relevant log lines (`docker compose logs SERVICE`
in the home). Remove passwords and addresses you do not want public.

**Changing something:**

- Small and one topic per pull request; for a new feature or a larger
  change, open an issue first and ask whether it fits. The reasons behind
  how things are now are in DECISIONS.md.
- Run the tests for what you touched (DEVELOPMENT.md): at least
  `tests/unit/run.sh`, and the acceptance test `tests/demo/run.sh` for
  anything that handles mail.
- Contributions come in under the project's licence, the GNU AGPL 3.0 or
  later (LICENSE).

**AI:** much of this project was written by an AI and reviewed and tested
by a human. AI-assisted contributions are welcome on the same terms: say
so, and the person sending the change has tested it and stands behind it.
