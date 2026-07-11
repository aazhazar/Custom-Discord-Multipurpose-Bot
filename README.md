# Custom-Discord-Multipurpose-Bot

# Discord Security Bot

> A powerful open-source Discord moderation and security bot built with **Python** and **discord.py**.

---

# 📋 Requirements

Before starting, install:

- Python **3.11 or newer**
- Git (optional)
- A Discord Bot Application
- A Google Gemini API Key (optional but recommended)

---

# 1. Download the Project

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Or click **Code → Download ZIP** on GitHub.

---

# 2. Install Python Packages

Open Command Prompt or Terminal inside the project folder.

Install:

```bash
pip install -U discord.py aiohttp
```

If that doesn't work:

```bash
pip install discord.py aiohttp
```

---

# 3. Create Your Discord Bot

1. Open https://discord.com/developers/applications
2. Click **New Application**
3. Create a Bot
4. Copy the Bot Token
5. Enable:
   - Server Members Intent
   - Message Content Intent
   - Presence Intent (if needed)

Invite the bot with Administrator permission.

---

# 4. Configure the Bot

Open **main.py**

### Bot Token

Find:

```python
TOKEN = "replace bot token here"
```

Replace with:

```python
TOKEN = "YOUR_DISCORD_BOT_TOKEN"
```

---

### Gemini API Key

Find:

```python
GEMINI_API_KEY = "replace gemini ai api key here"
```

Replace with your API key.

If you don't want AI moderation:

```python
GEMINI_API_KEY = ""
```

---

### Owner User ID

Find:

```python
AUTHORIZED_IDS = [
    "REPLACE YOUR USERID",
]
```

Replace with your Discord User ID.

Example:

```python
AUTHORIZED_IDS = [
    123456789012345678
]
```

---

### Main Server ID

Find:

```python
SOURCE_GUILD_ID = "MAIN SERVER ID"
```

Replace with your server ID.

---

### Logs Server ID

Find:

```python
DEST_GUILD_ID = "LOGS SERVER ID"
```

Replace with the server that stores mirrored logs.

---

### Role IDs

Replace:

```python
MOD_ROLE_ID
MOD_ROLE_LOW_ID
GOVERNOR_ROLE_ID
```

with your own Discord role IDs.

---

# 5. Run the Bot

```bash
python main.py
```

If successful you should see the bot come online.

---

# 6. Hosting for FREE (OriHost)

Website:

https://orihost.com/

## Step 1

Create a free Python server.

## Step 2

Upload every project file.

## Step 3

Startup command:

```bash
python main.py
```

(or whatever your main file is called)

## Step 4

Install packages from the console:

```bash
pip install -U discord.py aiohttp
```

## Step 5

Start the server.

Your bot should now stay online 24/7.

---

# Project Files

```
main.py
data.json
backups.json
```

Do not delete `data.json` or `backups.json`.
The bot creates them automatically if needed.

---

# Troubleshooting

## ModuleNotFoundError

Install packages again:

```bash
pip install -U discord.py aiohttp
```

## Invalid Token

Check your bot token.

## Missing Permissions

Give the bot **Administrator** permission.

## Commands Don't Work

Enable:

- Server Members Intent
- Message Content Intent

inside the Discord Developer Portal.

---

# Security

Never upload:

- Bot Token
- API Keys
- Personal IDs

Use environment variables if deploying publicly.

---

# License

Feel free to modify and contribute through Pull Requests.

If you improve the project, please consider sharing your changes with the community.
