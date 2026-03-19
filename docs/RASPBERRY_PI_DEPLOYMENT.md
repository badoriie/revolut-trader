# Raspberry Pi Deployment

This guide covers running revolut-trader on a Raspberry Pi (headless, no desktop app).

## Prerequisites

### Supported Hardware

| Model            | Architecture | Supported                             |
| ---------------- | ------------ | ------------------------------------- |
| Pi 4 / Pi 5      | ARM64        | Yes                                   |
| Pi 3 (64-bit OS) | ARM64        | Yes                                   |
| Pi 3 (32-bit OS) | ARMv7        | No — 1Password CLI has no ARMv7 build |
| Pi Zero / Pi 2   | ARMv6/ARMv7  | No                                    |

Use a 64-bit OS (Raspberry Pi OS Lite 64-bit) on Pi 3/4/5.

### Install 1Password CLI

```bash
curl -sS https://downloads.1password.com/linux/debian/arm64/stable/1password-cli-arm64-latest.deb -o op.deb
sudo dpkg -i op.deb
rm op.deb
op --version
```

______________________________________________________________________

## Authentication — Service Account (recommended)

Service accounts are the correct approach for unattended headless operation.
No master password, no biometric, no session expiry to manage.

### 1. Create the service account

1. Go to 1Password.com → your account → **Integrations** → **Service Accounts**
1. Click **New Service Account**, name it (e.g. `revolut-trader-pi`)
1. Grant it access to the `revolut-trader` vault:
   - **Read** — required for fetching credentials and config
   - **Write** — required only if you run `make ops` or `make opconfig-set` from the Pi
1. Copy the generated token — it is shown **only once**

### 2. Configure the Pi

```bash
# Add to ~/.bashrc (or ~/.profile for non-interactive shells)
echo 'export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...' >> ~/.bashrc
source ~/.bashrc

# Verify it works
op account list
make opstatus
```

### 3. Run the bot

```bash
make setup       # first-time setup (installs deps, pre-commit hooks)
make run-paper   # paper trading
```

______________________________________________________________________

## Running as a systemd service (unattended)

Create `/etc/systemd/system/revolut-trader.service`:

```ini
[Unit]
Description=Revolut Trader Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/revolut-trader
Environment=OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
ExecStart=/home/pi/revolut-trader/.venv/bin/python cli/run.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable revolut-trader
sudo systemctl start revolut-trader
sudo systemctl status revolut-trader
```

______________________________________________________________________

## Fallback — Interactive sign-in (personal accounts without service accounts)

If a service account is not available, sign in manually before each run:

```bash
eval $(op signin) && make run-paper
```

The session stays active for 30 minutes. For longer runs, renew it in a new terminal:

```bash
eval $(op signin)
```

______________________________________________________________________

## Troubleshooting

**`1Password is required but not available`**
The CLI is not authenticated. Set `OP_SERVICE_ACCOUNT_TOKEN` or run `eval $(op signin)`.

**`op: command not found`**
Install the ARM64 CLI package (see Prerequisites above).

**Architecture mismatch**
Run `uname -m` — it must return `aarch64`. If it returns `armv7l`, reinstall with a 64-bit OS.

**Session expires mid-run**
Switch to a service account (no expiry) or restart the bot after `eval $(op signin)`.
