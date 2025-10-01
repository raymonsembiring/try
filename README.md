### n8n Template: Send Email via Google Workspace (Gmail SMTP)

This repository provides a ready-to-import n8n workflow JSON to send emails using a Google Workspace (Gmail) user through SMTP.

#### Files
- `n8n-template-gmail-smtp.json`: n8n workflow export using the `Send Email` node (SMTP)
- `n8n-template-bulk-telegram-smtp.json`: n8n workflow to bulk‑send emails when a Telegram bot receives `/send`

#### Why SMTP?
Using the `Send Email` (SMTP) node is stable across n8n versions and straightforward to configure with a Gmail App Password. It works for personal Gmail and Google Workspace users where SMTP is allowed.

### Prerequisites
- Google Workspace (or Gmail) account with 2‑Step Verification enabled
- App Password generated for the account (for SMTP)
- n8n instance (cloud or self-hosted) with access to the internet

### Gmail App Password Setup
1. In your Google Account, go to Security → 2‑Step Verification and enable it.
2. In Security → App passwords, create a new app password (choose app "Mail", device "Other" or as you prefer). Copy the generated 16‑character password.

### Create SMTP Credentials in n8n
1. In n8n, open Credentials → New → "SMTP" (Send Email).
2. Configure:
   - User: your Gmail address (e.g., `your-user@your-domain.com`)
   - Password: your App Password (not your normal Google password)
   - Host: `smtp.gmail.com`
   - Port: `465` (SSL) or `587` (TLS)
   - SSL/TLS: enabled
3. Save the credential (note its name).

### Import the Workflow
1. In n8n, click Workflows → Import from File.
2. Select `n8n-template-gmail-smtp.json`.
3. Open the imported workflow and select the `Send Email` node.
4. In the node's Credentials, pick your SMTP credential created above.
5. Optionally edit `fromEmail` to match the mailbox or send‑as alias.

### What the Workflow Does
- Starts with `Manual Trigger`.
- `Set Email Fields` defines `to`, `subject`, `text`, and `html` fields.
- `Send Email` uses those fields to send via Gmail SMTP.

### Customize
- Update the `Set Email Fields` node values for `to`, `subject`, `text`, and `html`.
- Use n8n expressions to map incoming data into those fields (e.g., from webhook, Google Sheets, etc.).
- Add CC/BCC/attachments in the `Send Email` node under Additional Fields as needed.

### Notes
- If your Workspace admin restricts SMTP, coordinate with them or use an alternative transport.
- For domain‑wide sending on behalf of multiple users, consider Gmail API with a service account and domain‑wide delegation (outside the scope of this SMTP template).

## Bulk Email via Telegram `/send`

`n8n-template-bulk-telegram-smtp.json` lets you trigger a bulk send from a Telegram bot with the `/send` command.

### Setup: Telegram Bot
1. Create a Telegram bot via BotFather and copy the bot token.
2. In n8n, create a `Telegram` credential with that token.
3. Import `n8n-template-bulk-telegram-smtp.json`.
4. Open nodes:
   - `Telegram Trigger`: select your Telegram credential. Choose webhook or polling. For webhook, expose your n8n URL.
   - `Send Email (SMTP)`: select the SMTP credential you made earlier.
   - `Build Recipients`: replace the inline list with your data source (Google Sheets, DB, HTTP, etc.).

### How it Works
- `Telegram Trigger` receives messages from the bot.
- `IF /send` checks if the text starts with `/send`.
- `Telegram Ack Start` replies to the chat that sending started.
- `Build Recipients` returns an array of items with fields: `to`, `subject`, `text`, `html`.
- `Split In Batches` iterates items and sends each via `Send Email (SMTP)`.
- After completion, `Telegram Ack Done` informs the chat.

### Customization
- Replace `Build Recipients` with: Google Sheets node, database query, or HTTP Request to fetch your audience.
- Adjust `batchSize` and introduce delays/throttling to respect Gmail sending limits.
- Personalize `subject/text/html` using expressions from your data rows.

### Usage
- In Telegram, send `/send` to your bot. The workflow starts and sends the bulk emails as configured.

### Rate Limits & Safety
- Gmail/Workspace enforces daily and per-minute limits. Add waits or queues if needed.
- Consider adding an `IF` to restrict who can trigger `/send` by checking `message.from.id`.

