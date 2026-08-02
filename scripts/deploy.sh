#!/usr/bin/env bash
# Run on the server after code arrives (or called over SSH by GitHub Actions).
# Usage (from repo root on the server):
#   ./scripts/deploy.sh
#
# Optional env:
#   DEPLOY_BRANCH          git branch to track (default: main)
#   TELEGRAM_BOT_SERVICE   systemd unit to restart (default: news-telegram-bot)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"
SERVICE="${TELEGRAM_BOT_SERVICE:-news-telegram-bot}"

echo "==> Deploying in $ROOT (branch: $BRANCH)"

if [[ ! -d .git ]]; then
  echo "error: $ROOT is not a git checkout" >&2
  exit 1
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating .venv"
  python3 -m venv .venv
fi

echo "==> Installing Python dependencies"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  echo "warning: .env is missing in $ROOT — create it on the server before ingest/bot will work" >&2
fi

if systemctl --user list-unit-files "${SERVICE}.service" &>/dev/null 2>&1; then
  echo "==> Restarting user systemd unit: ${SERVICE}"
  systemctl --user restart "${SERVICE}.service"
  systemctl --user --no-pager --full status "${SERVICE}.service" || true
elif systemctl list-unit-files "${SERVICE}.service" &>/dev/null 2>&1; then
  echo "==> Restarting system systemd unit: ${SERVICE} (may need passwordless sudo)"
  if sudo -n systemctl restart "${SERVICE}.service" 2>/dev/null; then
    sudo -n systemctl --no-pager --full status "${SERVICE}.service" || true
  else
    echo "warning: could not restart ${SERVICE}.service (install unit + allow sudo -n, or restart manually)" >&2
  fi
else
  echo "note: no systemd unit named ${SERVICE}.service — skipped bot restart"
  echo "      (install deploy/news-telegram-bot.service or restart the polling process yourself)"
fi

echo "==> Deploy finished"
