# Invoked by the "Tradysquid Evolve Bot Weekly Review" scheduled task
# (weekly, Monday morning, before market open). Three real steps, in
# order:
#   1. Refresh anything that only changes when the underlying data
#      changes (retrain_loop, logic_proposals - both cheap/idempotent
#      no-ops most weeks, see their own module docstrings) and refresh
#      the Discord dashboard. This was never wired to run automatically
#      anywhere before this script - found and fixed the same session as
#      the trading-loop scheduling gap.
#   2. A non-interactive `claude -p` session that reads weekly_review.py's
#      real numbers and writes a genuine assessment to evolve_bot/reviews/.
#      Read-only against everything except that one new file per run; the
#      prompt itself (weekly_review_prompt.txt) explicitly instructs no
#      git operations and no edits outside evolve_bot/reviews/.
#   3. Post that review file to Discord's #evolve-reviews.
#
# --tools "Read,Write,Bash" + --permission-mode bypassPermissions: step 2
# runs fully unattended (no TTY to answer a permission prompt), so the
# safety boundary is the restricted tool set, not per-call approval -
# no Edit tool at all, and nothing outside those three.

$ErrorActionPreference = "Continue"
Get-Content "C:\Tradysquid\.env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        if (-not (Test-Path "env:$($parts[0].Trim())")) {
            Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
        }
    }
}
Set-Location "C:\Tradysquid\evolve_bot"

$reviewsDir = "C:\Tradysquid\evolve_bot\reviews"
if (-not (Test-Path $reviewsDir)) {
    New-Item -ItemType Directory -Path $reviewsDir -Force | Out-Null
}

$logPath = Join-Path $reviewsDir "weekly_review_log.txt"
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logPath -Value "=== Weekly review run started $startedAt ==="

$python = "..\.venv-evolve\Scripts\python.exe"
$step1 = & $python -c "import json, retrain_loop, logic_proposals, presentation; print(json.dumps({'retrain': retrain_loop.run_retrain_cycle()['status'], 'proposals': logic_proposals.run_proposal_cycle()['status'], 'dashboard': presentation.post_dashboard()['status']}))" 2>&1
Add-Content -Path $logPath -Value "--- refresh step: $step1 ---"

Set-Location "C:\Tradysquid"
$prompt = Get-Content -Raw "C:\Tradysquid\evolve_bot\weekly_review_prompt.txt"
& claude -p $prompt --permission-mode bypassPermissions --tools "Read,Write,Bash" --output-format text *>> $logPath

$latestReview = Get-ChildItem $reviewsDir -Filter "*_weekly_review.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestReview) {
    Set-Location "C:\Tradysquid\evolve_bot"
    $postResult = & $python -c "import discord_post; content=open(r'$($latestReview.FullName)', encoding='utf-8').read(); print(discord_post.post_file('reviews', __import__('pathlib').Path(r'$($latestReview.FullName)'), content='**Weekly review**', mime_type='text/markdown'))" 2>&1
    Add-Content -Path $logPath -Value "--- posted review to discord: $postResult ---"
}

$finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logPath -Value "=== Weekly review run finished $finishedAt ==="
