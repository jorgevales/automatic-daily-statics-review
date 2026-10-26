# Case Review Runner: Purpose and Scope

## Intended purpose
Automate submitting prepared instruction-change cases to Microsoft 365 Copilot for review, using an installed Microsoft Edge browser. The program manages the workflow; the two supplied Markdown files define the review instructions and the message sent to Copilot.

## Main workflow
1. Accept a root folder containing separate case folders, each identified by an instruction ID and account number.
2. Discover and validate the evidence, including one audit trail/history and one Register account snapshot. Check that the snapshot account matches the case folder, and always exclude `.edge-debug-9223`.
3. Copy the evidence and instructions into a separate staging area without modifying the originals. Block cases exceeding the 20-attachment limit, including the instructions file.
4. Use up to six parallel browser slots, with one case per fresh Copilot conversation. Attach the instructions and evidence, then add the base message and case-identification details.
5. Confirm the attachments and message before submitting. Monitor the response and save the captured response, case status, diagnostics and run summary.

## Important boundaries
- The default run submits real evidence. `--discover-only` validates and reports without submitting or claiming cases.
- Persistent case records and claims prevent automatic duplicate submissions. Uncertain sends are not replayed; unresolved cases require reconciliation.
- A captured, completed response does not independently prove that the audit finding is correct. Structured results are checked only when the base message declares the supported completion contract.
- Python-managed storage and dependencies are restricted to S:. Installed Edge is the permitted executable outside S:; Windows and Edge operating-system activity is outside the program's control.
- The package consists of a CMD launcher, a single Python runner and two Markdown resources. Missing Python dependencies are installed automatically; no browser download or administrator elevation is intended.

## Current blocking error: first issue to fix
The original, unsanitized program failed during Edge startup. Fix this issue before making unrelated changes or attempting real case submissions.

### Observed run
- Case discovery completed: 5 cases found, all 5 ready, with 0 discovery issues.
- The excluded browser-profile folder was correctly skipped.
- The program attempted to start its dedicated Edge browser, but its debugging endpoint did not become available within the approximately 60-second startup wait.
- The run stopped with exit code 1 at browser startup, before the case-submission stage.

### Reported error
```text
RuntimeError: Edge endpoint did not become available.
The cause is not yet established.
Review the startup diagnostics and captured browser output;
no automatic relaunch or profile deletion was attempted.
```

The failure originated in `_ensure_started_once()`, called through `ensure_started()` and `execute_simple()`.

### Investigation priority
Inspect the startup diagnostics JSON and captured browser stderr log to establish the cause. The console output alone does not establish whether the problem involves browser startup, debugging access, the selected port, profile storage, permissions or company policy. Do not assume that changing the port will fix it.

The program reported that it did not attempt administrator elevation, a browser download or a personal-drive storage fallback. Preserve those restrictions, the S: storage requirement and the existing duplicate-submission safeguards when fixing the issue. Do not automatically delete profiles or replay uncertain submissions.

### Diagnostic privacy
The original console output contains internal server names, network shares, folder structures, user-specific identifiers and run identifiers. They are intentionally omitted here. Startup diagnostics and browser logs have not been supplied with this overview and must be sanitized separately before sharing.

## Shared source copies
The sanitized Python and CMD copies replace internal Python, Node and runtime locations with generic S: placeholders. They are for source review, not direct execution. Restore the actual paths and expected filenames before running. Runtime logs, settings and case evidence are not included in this sanitization.
