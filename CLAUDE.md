# Claude Tradysquid Instructions

Read and follow `AGENTS.md` before changing this repository.

Claude shares this checkout with Codex. Do not begin an edit until
`ai_coordination.py begin --actor Claude` acquires the OneDrive update lock.
Treat GitHub `main` as the authoritative code and the OneDrive control folder
as the audit trail. Record what changed, how it was implemented, tests run,
affected files, and the final commit through `ai_coordination.py finish`.

Do not use brokerage execution tools. Do not expose secrets. Do not act on
member suggestions unless the owner approved them.
