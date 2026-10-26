# Automatic daily statics review

Sends prepared instruction-change cases to Microsoft 365 Copilot for review through an installed Microsoft Edge,
one case per fresh conversation. Built for the VDI and the shared `S:` drive. See
[docs/program_overview.md](docs/program_overview.md) for what it does and its safety rules.

## Files

| File | What it is |
|---|---|
| `Run_case_reviews.cmd` | Normal run. Double-click, then paste the case root folder (or drag the folder onto it). |
| `Run_case_reviews_DIAGNOSE.cmd` | The same real run, recorded in full, with two reports at the end (see below). |
| `Run_case_reviews_DIAGNOSE_ALT.cmd` | Same as DIAGNOSE, but Edge uses your normal Windows user folders. Only for when the report suggests it. |
| `case_review_runner.py` | The program itself. |
| `local_paths.example.cmd` | Example of the file the first run creates for you. |
| `tests/` | Offline checks for the diagnose reports (`python -m unittest discover -s tests`). |

Put your two Markdown files (`daily_review_instructions.md`, `daily_review_base_message.md`) next to the runner.
They are ignored by Git on purpose, so copy them in by hand.

## First run on the VDI

1. Copy this folder to `S:`.
2. Double-click `Run_case_reviews.cmd`. It asks, in plain English, for three S: paths (Python, Node.js, a working
   folder), checks them, and saves them in `local_paths.cmd` on that computer. Delete that file to be asked again.
3. Sign in to Copilot by hand in the dedicated Edge window the first time. The sign-in is kept in the S: profile.

## Reading a failed run

Run `Run_case_reviews_DIAGNOSE.cmd`. It behaves like a normal run (it **does** submit real cases; the existing
duplicate-submission protection still applies) and writes, in `<runtime>\users\<you>\logs\diagnose\<date-time>\`:

* `INTERNAL_do_not_share.md` - everything, including real paths and names. Stays inside the VDI. It ends with a key that
  says what each label in the external report stood for.
* `EXTERNAL_safe_to_share.md` - the same story with identifying values replaced by numbered labels such as
  `<PATH-3 S: depth=4 ext=.json>`, plus a table of what was removed. Safe to send back for help.
* `events.jsonl` - the raw event log, internal.

The terminal also prints the likely cause in plain English.

## Edge startup notes

* The dedicated Edge uses port 9237 and never touches other Edge debugging sessions (for example on 9223).
* The tool waits up to 120 seconds for Edge's debugging port and prints progress every 10 seconds.
* It never relaunches, deletes a profile, changes policy, or replays an uncertain submission.
