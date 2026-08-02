# OpenAI Discord Upgrader

This upgrade keeps Tradysquids' existing Learning Center and adds OpenAI as an
AI explanation layer for `/ask`. The local answer is generated first and is
used as grounding. If OpenAI is unavailable, the bot falls back to the local
answer instead of breaking the command.

## Private local configuration

On the Windows laptop that runs Tradysquids, open the repository's ignored
`.env` file and add the project API key:

```env
OPENAI_API_KEY=sk-proj-your-complete-key
OPENAI_MODEL=gpt-5-mini
```

Never put the real key in `.env.example`, GitHub source code, Discord, an issue,
a screenshot, or chat.

Optional controls:

```env
OPENAI_MAX_OUTPUT_TOKENS=700
OPENAI_REQUEST_TIMEOUT_SECONDS=30
OPENAI_USER_COOLDOWN_SECONDS=8
```

The per-user cooldown limits accidental API spending when multiple Discord
members repeatedly call `/ask`.

## Install and restart

From PowerShell in the repository:

```powershell
python -m pip install -r requirements.txt
python run_with_env.py register_discord_commands.py
```

Then restart Tradysquids with the normal launcher:

```powershell
.\START-TRADYSQUID.bat
```

## Test

In Discord:

```text
/ask question: Explain how theta and IV affect a 30 DTE credit spread.
/ask question: Why can a correct directional call still lose money?
```

The response footer identifies an AI-assisted answer. Current quotes, chains,
charts, filings, and tracked performance must still come from the bot's live
commands.

## Safety and failure behavior

- The OpenAI key is read only from the local process environment.
- No command places a brokerage trade.
- The AI instructions prohibit naked short-option recommendations and blind
  buy/sell alerts.
- Missing packages, invalid keys, timeouts, rate limits, and network failures
  return the existing local Learning Center answer with a short diagnostic.
- The API request sends the user's question and the generated educational local
  answer. It does not send the `.env`, API key, Discord token, or brokerage
  credentials.
