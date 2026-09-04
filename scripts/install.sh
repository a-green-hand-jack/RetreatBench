#!/usr/bin/env bash
set -euo pipefail

# One-step installer for the Harbor plugin and the OpenCode recorder. It is
# idempotent and keeps Python dependencies in a user-owned virtualenv.
die() { printf 'retreatbench install error: %s\n' "$*" >&2; exit 1; }
info() { printf 'retreatbench install: %s\n' "$*"; }
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [ -f "$SCRIPT_SOURCE" ] && [ -f "$(dirname "$SCRIPT_SOURCE")/../pyproject.toml" ]; then
  ROOT="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"
  FROM_CHECKOUT=1
else
  # When this file is piped from curl there is no checkout to install from.
  # Keep a shallow, user-owned source copy so the editable plugin can still be
  # installed and later upgraded by rerunning this command.
  ROOT="${RETREATBENCH_SOURCE_DIR:-${HOME}/.retreatbench/source}"
  FROM_CHECKOUT=0
fi
VENV="${RETREATBENCH_VENV:-${HOME}/.retreatbench/venv}"
HARBOR_VERSION="${RETREATBENCH_HARBOR_VERSION:-0.20.0}"

install_system_deps() {
  [ "$(uname -s)" = "Linux" ] || die "automatic system dependency installation currently supports Ubuntu/Debian Linux only; install Python >=3.11, Node >=20, npm, Docker, git, and curl manually"
  command -v apt-get >/dev/null 2>&1 || die "apt-get is required for automatic dependency installation; install Python >=3.11, Node >=20, npm, Docker, git, and curl manually"
  if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
  else
    command -v sudo >/dev/null 2>&1 || die "sudo is required to install missing system dependencies"
    SUDO="sudo"
  fi

  local packages=(ca-certificates curl git python3 python3-venv python3-pip docker.io)
  local missing=()
  for package in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    info "installing system packages: ${missing[*]}"
    $SUDO apt-get update
    $SUDO apt-get install -y "${missing[@]}"
  fi

  if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || printf 0)" -lt 20 ]; then
    info "installing Node.js 20"
    if [ -n "$SUDO" ]; then
      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    else
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    fi
    $SUDO apt-get install -y nodejs
  fi

  if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
  fi
}

# v1 deliberately has one supported host contract.  Fail clearly before any
# repository clone or user-directory mutation on other operating systems.
[ "$(uname -s)" = "Linux" ] || die "RetreatBench v1 supports Ubuntu/Debian Linux only; install Python >=3.11, Node >=20, npm, Docker, git, and curl manually"
[ -x "$(command -v apt-get 2>/dev/null || true)" ] || die "RetreatBench v1 requires apt-get on Ubuntu/Debian; install Python >=3.11, Node >=20, npm, Docker, git, and curl manually"

if ! command -v python3 >/dev/null 2>&1 \
  || ! command -v node >/dev/null 2>&1 \
  || ! command -v npm >/dev/null 2>&1 \
  || ! command -v docker >/dev/null 2>&1 \
  || ! command -v git >/dev/null 2>&1 \
  || ! command -v curl >/dev/null 2>&1; then
  install_system_deps
fi

if [ "$FROM_CHECKOUT" -eq 0 ] && [ ! -f "$ROOT/pyproject.toml" ]; then
  mkdir -p "$(dirname "$ROOT")"
  git clone --depth 1 "${RETREATBENCH_REPO_URL:-https://github.com/a-green-hand-jack/RetreatBench.git}" "$ROOT"
fi

command -v python3 >/dev/null 2>&1 || die "python3 installation failed"
command -v node >/dev/null 2>&1 || die "Node.js installation failed"
command -v npm >/dev/null 2>&1 || die "npm installation failed"
command -v docker >/dev/null 2>&1 || die "Docker installation failed"
command -v curl >/dev/null 2>&1 || die "curl installation failed"
command -v git >/dev/null 2>&1 || die "git installation failed"
docker info >/dev/null 2>&1 || die "Docker is installed but its daemon is not available to the current user; start Docker and rerun the installer"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 20 ] || die "Node.js >= 20 is required; found $(node -v)"

PYTHON_BIN="python3"
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION##*.}"
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
  if ! command -v python3.11 >/dev/null 2>&1; then
    [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null 2>&1 || die "Python >= 3.11 is required; install python3.11 and python3.11-venv"
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
    $SUDO apt-get update
    $SUDO apt-get install -y python3.11 python3.11-venv
  fi
  PYTHON_BIN="python3.11"
fi

mkdir -p "$(dirname "$VENV")"
if ! "$PYTHON_BIN" -m venv "$VENV" 2>/dev/null; then
  command -v uv >/dev/null 2>&1 || die "python3-venv or uv is required to create $VENV"
  uv venv --clear --system-site-packages "$VENV" >/dev/null
fi
if [ -x "$VENV/bin/pip" ]; then
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/python" -m pip install -e "${ROOT}[dev]" >/dev/null
  "$VENV/bin/python" -m pip install "harbor==${HARBOR_VERSION}" >/dev/null
else
  command -v uv >/dev/null 2>&1 || die "pip or uv is required to install Python dependencies"
  uv pip install --python "$VENV/bin/python" -e "${ROOT}[dev]" "harbor==${HARBOR_VERSION}" >/dev/null
fi
export PATH="$VENV/bin:$PATH"

# Harbor installed by uv may run from its own isolated interpreter. Install the
# plugin bridge into that interpreter as well, so a pre-existing `harbor`
# command can resolve `retreatbench.harbor_plugins` without a PYTHONPATH hack.
HARBOR_BIN="$(command -v harbor || true)"
if [ -n "$HARBOR_BIN" ] && [ "$HARBOR_BIN" != "$VENV/bin/harbor" ]; then
  HARBOR_PYTHON="$(sed -n '1s/^#!//p' "$HARBOR_BIN" 2>/dev/null || true)"
  if [ -x "$HARBOR_PYTHON" ] && command -v uv >/dev/null 2>&1; then
    uv pip install --python "$HARBOR_PYTHON" -e "$ROOT" >/dev/null
  fi
fi

if ! command -v opencode >/dev/null 2>&1; then
  if [ "${RETREATBENCH_SKIP_OPENCODE_INSTALL:-0}" != "1" ]; then
    curl -fsSL https://opencode.ai/install | bash
    export PATH="${HOME}/.local/bin:${HOME}/bin:${PATH}"
  fi
fi

if [ -f "$ROOT/packages/retreat-recorder/package.json" ]; then
  npm install --prefix "$ROOT/packages/retreat-recorder" --no-fund --no-audit >/dev/null
  npm link --prefix "$ROOT/packages/retreat-recorder" >/dev/null
fi

if command -v harbor >/dev/null 2>&1; then
  printf 'Harbor: %s\n' "$(harbor --version 2>/dev/null || printf installed)"
else
  printf 'Harbor installed in %s/bin; add it to PATH:\n  export PATH="%s/bin:$PATH"\n' "$VENV" "$VENV"
fi
printf 'RetreatBench: %s\n' "$("$VENV/bin/retreatbench" version)"
if command -v retreat-recorder >/dev/null 2>&1; then
  retreat-recorder doctor
fi
command -v opencode >/dev/null 2>&1 || printf 'OpenCode: not found (set RETREATBENCH_SKIP_OPENCODE_INSTALL=0 and rerun)\n'
printf '\nInstall complete. Run a task with standard Harbor syntax and one plugin:\n'
printf '  harbor run ... -a codex -m gpt-5.6-terra --plugin retreatbench.harbor_plugins:RecorderExportBoth\n'
