# Free Discord to GitHub Upgrade Batches

This bridge lets the configured Discord owner collect upgrade requests in a
GitHub Issue without using the OpenAI API. It does not edit code, approve its own
work, merge pull requests, or place trades.

## What the commands do

Use these owner-only slash commands in `#upgrade-review`:

```text
/upgrade-add request:Add IV percentile to option cards
/upgrade-add request:Show the exact rejection reason on scanner cards
/upgrade-list
/upgrade-ready summary:Implement these as one options-card cleanup batch
```

Each `/upgrade-add` call becomes a separate comment on one open GitHub Issue.
`/upgrade-ready` renames that issue to a READY batch. The next `/upgrade-add`
starts a new issue automatically.

Use `/upgrade-cancel reason:` to close an unwanted open batch. Ordinary Discord
messages are not uploaded; only these owner-only slash commands trigger GitHub.

## One-time GitHub token

Create a fine-grained personal access token for the account that owns the
repository. Limit it to:

- Repository access: only `Angrysquid46/Tradysquid`
- Repository permission: Issues, read and write
- Metadata: read (GitHub includes this automatically)

The token does not need repository Contents write access because the bot only
creates and updates Issues and comments.

Add it to the ignored local `.env` on the Windows laptop:

```env
GITHUB_UPGRADE_TOKEN=github_pat_your_complete_token
GITHUB_REPOSITORY=Angrysquid46/Tradysquid
```

Never put the real token in `.env.example`, Discord, GitHub code, screenshots,
issues, or chat.

## Install and verify

The background supervisor normally pulls merged changes and registers slash
commands automatically. For a manual refresh:

```powershell
cd "C:\Users\strea\OneDrive\Desktop\Tradysquid-main"
git pull origin main
python run_with_env.py register_discord_commands.py
.\START-TRADYSQUID.bat
```

Then run:

```text
/upgrade-list
```

A missing or under-permissioned token produces a safe Discord error without
exposing the token.

## Batch implementation workflow

1. Collect requests with `/upgrade-add`.
2. Review the count with `/upgrade-list`.
3. Lock the batch with `/upgrade-ready`.
4. In ChatGPT, request: `Review the latest ready Tradysquid upgrade batch.`
5. The maintainer reads the GitHub Issue, inspects current code, creates a tested
   branch and pull request, and merges only after validation.
6. The existing supervisor pulls approved `main`, validates it, restarts the
   services, and reports deployment status.

No OpenAI API credit is used by this batching path.
