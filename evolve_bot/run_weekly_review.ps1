# Invoked by the "Tradysquid Evolve Bot Weekly Review" scheduled task
# (weekly, Monday morning, before market open) - runs a non-interactive
# `claude -p` session that reads weekly_review.py's real numbers and
# writes a genuine assessment to evolve_bot/reviews/. Read-only against
# everything except that one new file per run; the prompt itself
# (weekly_review_prompt.txt) explicitly instructs no git operations and
# no edits outside evolve_bot/reviews/.
#
# --tools "Read,Write,Bash" + --permission-mode bypassPermissions: this
# runs fully unattended (no TTY to answer a permission prompt), so the
# safety boundary is the restricted tool set, not per-call approval -
# no Edit tool at all, and nothing outside those three.

$ErrorActionPreference = "Continue"
Set-Location "C:\Tradysquid"

$reviewsDir = "C:\Tradysquid\evolve_bot\reviews"
if (-not (Test-Path $reviewsDir)) {
    New-Item -ItemType Directory -Path $reviewsDir -Force | Out-Null
}

$logPath = Join-Path $reviewsDir "weekly_review_log.txt"
$prompt = Get-Content -Raw "C:\Tradysquid\evolve_bot\weekly_review_prompt.txt"
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Add-Content -Path $logPath -Value "=== Weekly review run started $startedAt ==="
& claude -p $prompt --permission-mode bypassPermissions --tools "Read,Write,Bash" --output-format text *>> $logPath
$finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logPath -Value "=== Weekly review run finished $finishedAt ==="
