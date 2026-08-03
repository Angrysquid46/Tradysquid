# Live acceptance boundary

The following checks require the production Windows computer and are not passed by GitHub code or isolated tests:

- one-click installation
- credential preservation
- live Tradier authentication and market reads
- live Discord authentication, commands, channels, journals, and reports
- Windows startup registration
- one running application process
- production scan and paper-cycle receipts
- update and rollback acceptance

Until those checks run, the overall rebuild result is `BLOCKED`, not `PASSED`.
