# Local test receipt

The replacement tree was assembled and tested in an isolated local checkout before being pushed.

- Command: `python -m compileall -q tradysquid scripts tests`
- Result: PASS
- Command: `python -m pytest -q`
- Result: 32 passed
- Runtime dependencies were not connected to private Discord or Tradier credentials during automated tests.
- Windows installation, Discord synchronization, Tradier live reads, scheduled startup, and rollback remain BLOCKED until run on the owner’s production computer.

This receipt proves local code checks only. It is not a deployment receipt.
