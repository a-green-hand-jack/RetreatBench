#!/usr/bin/env bash
set -euo pipefail

# One-step installer for the Harbor plugin and the OpenCode sidecar. It is
# idempotent and keeps Python dependencies in a user-owned virtualenv.
die() { printf 'retreatbench install error: %s\n' "$*" >&2; exit 1; }
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [ -f "$SCRIPT_SOURCE" ] && [ -f "$(dirname "$SCRIPT_SOURCE")/../pyproject.toml" ]; then
  ROOT="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"
else
  # When this file is piped from curl there is no checkout to install from.
  # Keep a shallow, user-owned source copy so the editable plugin can still be
  # installed and later upgraded by rerunning this command.
  ROOT="${RETREATBENCH_SOURCE_DIR:-${HOME}/.retreatbench/source}"
  if [ ! -f "$ROOT/pyproject.toml" ]; then
    command -v git >/dev/null 2>&1 || die "git is required for curl-based installation"
    mkdir -p "$(dirname "$ROOT")"
    git clone --depth 1 "${RETREATBENCH_REPO_URL:-https://github.com/a-green-hand-jack/RetreatBench.git}" "$ROOT"
  fi
fi
VENV="${RETREATBENCH_VENV:-${HOME}/.retreatbench/venv}"
HARBOR_VERSION="${RETREATBENCH_HARBOR_VERSION:-0.20.0}"

command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v node >/dev/null 2>&1 || die "Node.js >= 20 is required"
command -v npm >/dev/null 2>&1 || die "npm is required"
command -v curl >/dev/null 2>&1 || die "curl is required to install OpenCode"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 20 ] || die "Node.js >= 20 is required; found $(node -v)"

mkdir -p "$(dirname "$VENV")"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install -e "${ROOT}[dev]" >/dev/null
"$VENV/bin/python" -m pip install "harbor==${HARBOR_VERSION}" >/dev/null
export PATH="$VENV/bin:$PATH"

if ! command -v opencode >/dev/null 2>&1; then
  if [ "${RETREATBENCH_SKIP_OPENCODE_INSTALL:-0}" != "1" ]; then
    curl -fsSL https://opencode.ai/install | bash
    export PATH="${HOME}/.local/bin:${HOME}/bin:${PATH}"
  fi
fi

if [ -f "$ROOT/packages/retreat-auditor/package.json" ]; then
  npm install --prefix "$ROOT/packages/retreat-auditor" --no-fund --no-audit >/dev/null
  npm link --prefix "$ROOT/packages/retreat-auditor" >/dev/null
fi

if command -v harbor >/dev/null 2>&1; then
  printf 'Harbor: %s\n' "$(harbor --version 2>/dev/null || printf installed)"
else
  printf 'Harbor installed in %s/bin; add it to PATH:\n  export PATH="%s/bin:$PATH"\n' "$VENV" "$VENV"
fi
printf 'RetreatBench: %s\n' "$("$VENV/bin/retreatbench" version)"
if command -v retreat-auditor >/dev/null 2>&1; then
  retreat-auditor doctor
fi
command -v opencode >/dev/null 2>&1 || printf 'OpenCode: not found (set RETREATBENCH_SKIP_OPENCODE_INSTALL=0 and rerun)\n'
printf '\nInstall complete. Run a task with standard Harbor syntax and one plugin:\n'
printf '  harbor run ... -a codex -m gpt-5.6-terra --plugin retreatbench.harbor_plugins:AvoidanceExportBoth\n'
