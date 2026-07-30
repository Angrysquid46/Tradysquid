# Tradysquids Discord Command Bot with ngrok

This local service adds private Discord slash commands for Ford charts and
trade information:

- `/chart [days]`
- `/levels`
- `/events`
- `/why trade_id`

The laptop must remain awake, connected to the internet, and running both the
Python service and ngrok.

## 1. Install the Python packages

Open PowerShell in this repository and run:

```powershell
python -m pip install -r requirements.txt
```

## 2. Create the private configuration

Copy `.env.example` to `.env`. The completed `.env` is ignored by Git and must
never be committed.

In the Discord Developer Portal, open the existing TradeBot application:

1. **General Information**
   - Copy **Application ID** to `DISCORD_APPLICATION_ID`.
   - Copy **Public Key** to `DISCORD_PUBLIC_KEY`.
2. **Bot**
   - Use the existing bot token for `DISCORD_BOT_TOKEN`.
   - Never paste the token into Discord, GitHub code, screenshots, or chat.
3. Add the existing server ID to `DISCORD_GUILD_ID`.
4. Optionally add your Discord user ID to `DISCORD_ALLOWED_USER_ID` to make
   commands usable only by you.
5. Add the existing Tradier values.
6. For SEC filing detail, use an identifiable value such as
   `Tradysquids TradeBot your-email@example.com` for `SEC_USER_AGENT`.

## 3. Register the commands

Run once, and again whenever command definitions change:

```powershell
.\register-commands.cmd
```

Guild commands normally appear in the selected server immediately.

## 4. Start the local command service

Keep this terminal open:

```powershell
.\start-command-bot.cmd
```

Confirm locally:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

## 5. Start ngrok

Open a second PowerShell window and run:

```powershell
ngrok http 8080
```

If Windows cannot find `ngrok`, run it by its full path, or add the folder
containing `ngrok.exe` to PATH.

Copy the HTTPS forwarding address shown by ngrok, for example:

```text
https://your-domain.ngrok-free.app
```

The Discord endpoint will be:

```text
https://your-domain.ngrok-free.app/interactions
```

## 6. Connect Discord to ngrok

In the Discord Developer Portal:

1. Open TradeBot.
2. Open **General Information**.
3. Find **Interactions Endpoint URL**.
4. Paste the complete ngrok `/interactions` URL.
5. Save changes.

Discord sends a signed PING. The service verifies the signature and returns the
required PONG. If either Python or ngrok is not running, Discord cannot save or
use the endpoint.

## 7. Test in Discord

In the Tradysquids server, type:

```text
/levels
/chart days:30
/events
/why trade_id:F-20260729-005
```

`/chart` defers immediately, builds a fresh PNG from Tradier data, and edits the
Discord response with the chart attached.

## Everyday startup

After restarting the laptop:

1. Start `.\start-command-bot.cmd`.
2. Start `ngrok http 8080`.
3. If the ngrok HTTPS domain changed, update Discord's Interactions Endpoint
   URL before using commands.

## Safety

- Requests without a valid Discord Ed25519 signature receive HTTP 401.
- The service accepts only the configured Discord server.
- Set `DISCORD_ALLOWED_USER_ID` to restrict commands to one account.
- The web server binds only to `127.0.0.1`; ngrok provides the public tunnel.
- No command places trades. Tradier access remains market-data-only.
- Keep `.env` private and rotate any token that is accidentally exposed.
