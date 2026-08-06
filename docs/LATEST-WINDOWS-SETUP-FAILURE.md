# Latest Windows setup failure

## Observed production boundary

- Previous clean-rebuild commit: `73a88470b459ac651df1efb473d30a4628b43cb5`
- Repository: `C:\Tradysquid\app`
- Original branch: `main`
- Clean branch switch: passed
- Canonical credential handoff verification: passed
- Canonical `.env` installation and reread: passed
- Failed outer stage: `clean-setup-process`
- Previous inner result: exit code `1` without the inner stage being surfaced
- Rollback: passed
- Final branch after rollback: `main`

The prior launcher did not expose the exact failing `scripts/setup.ps1` stage. It is therefore not truthful to invent a more specific historical error from the outer exit code alone.

## Corrective implementation

The clean rebuild now:

- records every setup stage with start, finish, duration, status, exit code, and sanitized error;
- prints the exact failed setup stage directly in the launcher console;
- preserves unrelated local `.env` settings while adding canonical aliases;
- starts Discord publishing before application readiness can pass;
- requires Discord connection, guild resolution, slash-command synchronization, channel synchronization, persistent-card bootstrap, and a system-health card before `START.cmd` reports PASS;
- wires universe, scan, paper-trade, strategy, diagnostics, reports, Learning Center, and journal refreshes into the application and scheduler.

## Automated verification

Windows GitHub Actions run `30795472228` on commit `ae333ae80c60c9452cb07037fbb6bbd617b649b9` completed successfully:

- isolated `.venv-tradysquid`: PASS
- editable project installation: PASS
- source compilation: PASS
- complete tests: 96 passed, 0 failed
- installation verifier from repository root: PASS
- import and installation verifier from an external path containing spaces: PASS

## Live retest

Live production installation, Discord publishing acknowledgements, and card update-in-place behavior remain BLOCKED until the Windows launcher is run against the tested commit. No live result is represented as passed from CI alone.
