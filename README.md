# Utility

A collection of utility scripts and libraries I use in different servers, Docker environments, and more. They offer consistent front-ends to tools I frequently use. Add `bin` to your `PATH`.

* `archive`: archives a directory (by default, puts result in $WORK).
* `unarchive`: un-archives a directory (by default, puts result in $WORK).
* `telegram-message`: sends a message to a Telegram bot.

## Install 

Usage requires `uv`. If you don't already have it, then download `uv` with the below (does not require root): 

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

Then install this package with the following:

```bash
uv sync
```

Usage of this package is done through the utility scripts above. For example, you may directly use `archive (path)`. 

## Secrets

*Secrets* may be provided in a "secrets.yaml" file at the root of this project (if you create this file, do not commit it), or its path may be provided with the `UTIL_SECRETS_PATH` environment variable. Secrets include the following:

* `TELEGRAM_CHAT_ID`: the chat identifier for a Telegram bot.
* `TELEGRAM_BOT_TOKEN`: the token for a Telegram bot. 
