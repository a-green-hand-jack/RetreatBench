#!/usr/bin/env bash
set -euo pipefail

OWNER="${GITHUB_OWNER:-a-green-hand-jack}"
REPO="${GITHUB_REPO:-RetreatBench}"
VISIBILITY="${GITHUB_VISIBILITY:-private}"
DESCRIPTION="Harbor-native evaluation of recoverable goal retreat in autonomous agents"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required." >&2
  exit 1
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Run this script from an initialized Git repository." >&2
  exit 1
fi
case "${VISIBILITY}" in
  public|private|internal) ;;
  *) echo "GITHUB_VISIBILITY must be public, private, or internal." >&2; exit 1 ;;
esac

gh auth status >/dev/null

if gh repo view "${OWNER}/${REPO}" >/dev/null 2>&1; then
  echo "Repository already exists: ${OWNER}/${REPO}" >&2
  exit 1
fi

gh repo create "${OWNER}/${REPO}" \
  "--${VISIBILITY}" \
  --description "${DESCRIPTION}"

REMOTE_URL="https://github.com/${OWNER}/${REPO}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
else
  git remote add origin "${REMOTE_URL}"
fi

git push -u origin HEAD:main

echo "Published https://github.com/${OWNER}/${REPO}"
