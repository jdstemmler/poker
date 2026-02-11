# Auto-Deploy Setup

Automatically rebuilds and deploys the poker game when changes are pushed to `main` on GitHub.

## How It Works

A lightweight shell script runs as a systemd service on the production machine. Every 60 seconds it runs `git fetch` and compares the local `main` branch to `origin/main`. When new commits are detected, it pulls and runs `docker compose up --build -d`.

## Setup (on the production machine)

### 1. Clone the repo (if not already done)

```bash
cd ~
git clone https://github.com/YOUR_USER/poker-game.git
cd poker-game
```

### 2. Make the deploy script executable

```bash
chmod +x deploy/auto-deploy.sh
```

### 3. Install the systemd service

Edit the service file to match your setup:

```bash
# Copy and edit — change YOUR_USER, REPO_DIR, and ADMIN_PASSWORD
sudo cp deploy/poker-deploy.service /etc/systemd/system/poker-deploy.service
sudo nano /etc/systemd/system/poker-deploy.service
```

Key values to update:
- `User=` — your Linux username
- `REPO_DIR=` — absolute path to the cloned repo
- `ADMIN_PASSWORD=` — your admin dashboard password

### 4. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now poker-deploy
```

### 5. Verify it's running

```bash
sudo systemctl status poker-deploy
journalctl -u poker-deploy -f
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `REPO_DIR` | (required) | Path to the cloned repo |
| `BRANCH` | `main` | Branch to watch |
| `POLL_INTERVAL` | `60` | Seconds between checks |
| `ADMIN_PASSWORD` | (empty) | Passed through to docker-compose |

## Workflow

After this is set up, the deploy cycle is:

1. Make changes on `develop`
2. Merge to `main`, tag, and push
3. Within 60 seconds, the production machine pulls and rebuilds automatically

## Logs

```bash
# Follow live
journalctl -u poker-deploy -f

# Last 50 lines
journalctl -u poker-deploy -n 50

# Since last boot
journalctl -u poker-deploy -b
```

## Troubleshooting

**Service won't start**: Check that `REPO_DIR` is correct and the user has permissions to the repo directory and Docker.

**Git fetch fails**: Make sure the production machine has network access to GitHub and the repo is cloned with HTTPS (or SSH keys are configured).

**Docker build fails**: Check `journalctl -u poker-deploy -f` for build errors. You can also manually run `docker compose up --build -d` in the repo directory to debug.

**Stop auto-deploy temporarily**:
```bash
sudo systemctl stop poker-deploy
```
