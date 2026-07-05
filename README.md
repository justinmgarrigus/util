# Utility

A collection of utility scripts and libraries I use in different servers, Docker environments, and more. They offer consistent front-ends to tools I frequently use.

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

In your `.bashrc`, add `source activate.csh`. Usage of these utility scripts are added through this activation script, allowing you to directly call them like `archive (path)`. When you install, it is recommended you run the tests to ensure everything works:

```bash

uv run pytest 
```

## Secrets

*Secrets* may be provided in a "secrets.yaml" file at the root of this project (if you create this file, do not commit it), or its path may be provided with the `UTIL_SECRETS_PATH` environment variable. Secrets include the following:

* `TELEGRAM_CHAT_ID`: the chat identifier for a Telegram bot.
* `TELEGRAM_BOT_TOKEN`: the token for a Telegram bot. 
* `RESEARCH_PATH`: base directory to where experiments/artifacts should be stored. 

## Contributing

After contributing code, lint your code and re-run the test cases:

```bash
uv run ruff format 
uv run ruff check --fix
uv run pytest 
```
