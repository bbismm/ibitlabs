#!/bin/bash
# deploy_web.sh — push web/public to Cloudflare Pages (canonical domain:
# ibitlabs.com; bibsus.com is the legacy mirror, in retirement).
#
# Reads CLOUDFLARE_API_TOKEN from .env so we don't have to paste it every
# time. The token is Pages:Edit scoped only — separate from CF_API_TOKEN
# which is KV-scoped. Both live in .env (gitignored).
#
# Usage:
#     scripts/deploy_web.sh

set -eu
cd /Users/bonnyagent/ibitlabs

# Load CLOUDFLARE_API_TOKEN from .env without leaking other vars to subshells.
if [ ! -f .env ]; then
    echo "ERROR: .env not found" >&2
    exit 1
fi
CLOUDFLARE_API_TOKEN=$(grep -E '^CLOUDFLARE_API_TOKEN=' .env | cut -d= -f2-)
if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo "ERROR: CLOUDFLARE_API_TOKEN not set in .env" >&2
    exit 1
fi
export CLOUDFLARE_API_TOKEN

echo "==> deploying web/ to Cloudflare Pages (bibsus) — reads wrangler.toml, includes functions/..."
cd web
npx wrangler pages deploy \
    --project-name=bibsus \
    --branch=main \
    --commit-dirty=true
