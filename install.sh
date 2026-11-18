#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
trap 'printf "Installation stopped at line %s; local data retained.\n" "$LINENO" >&2' ERR
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $EUID == 0 ]] || fail 'Run with sudo bash (or as root).'
# Never read prompts from stdin: it may contain the rest of curl | bash.
prompt() {
  local name=$1 label=$2
  [[ -e /dev/tty ]] || fail "No terminal: supply $name in the environment."
  printf '%s: ' "$label" >/dev/tty
  IFS= read -r -s "$name" </dev/tty || fail "Unable to read $name; supply it in the environment."
  printf '\n' >/dev/tty
}
source /etc/os-release
[[ $ID == debian || $ID == ubuntu ]] || fail 'Only Debian and Ubuntu are supported.'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 iproute2 util-linux
# Download to files: fail closed on HTTP errors, rather than a successful empty pipe.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if ! command -v docker >/dev/null; then
  curl --proto '=https' --tlsv1.2 -fsSL https://get.docker.com -o "$tmp/docker.sh"
  sh "$tmp/docker.sh"
fi
docker compose version >/dev/null || fail 'Docker Compose plugin missing; install docker-compose-plugin for your Docker distribution.'
systemctl enable --now docker
if ! command -v netbird >/dev/null; then
  curl --proto '=https' --tlsv1.2 -fsSL https://pkgs.netbird.io/install.sh -o "$tmp/netbird.sh"
  bash "$tmp/netbird.sh"
fi
systemctl enable --now netbird
ROOT=${INSTALL_DIR:-/opt/ai-stack}
[[ $ROOT == /* && $ROOT != / && $ROOT != *[$'\n\r\t ']* ]] || fail 'INSTALL_DIR must be an absolute path without whitespace.'
if [[ ! -e $ROOT ]]; then
  git clone --branch main https://github.com/sharman35/ai-stack.git "$ROOT"
else
  [[ -f $ROOT/docker-compose.yml && -f $ROOT/scripts/prepare.py ]] || fail 'Existing INSTALL_DIR is not ai-stack; refusing to overwrite.'
fi
cd "$ROOT"
exec 9>"$ROOT/.install.lock"
flock -n 9 || fail 'Another installer is running.'
# Do not reconnect an already enrolled peer or silently move another deployment.
if netbird status 2>/dev/null | python3 -c 'import sys; s=sys.stdin.read(); sys.exit(not ("Management: Connected" in s and "https://netbird.rusoft54.ru" in s))'; then
  :
else
  # Detailed status includes the management URL; some releases omit it in brief status.
  status=$(netbird status -d 2>/dev/null || true)
  if [[ $status == *'Management: Connected'* && $status == *'https://netbird.rusoft54.ru'* ]]; then
    :
  else
    [[ $status != *'Management: Connected'* ]] || fail 'NetBird already connected to another/unknown management server. Review manually; not switching it.'
    [[ -n ${NB_SETUP_KEY:-} ]] || prompt NB_SETUP_KEY 'NetBird setup key (hidden)'
    [[ -n $NB_SETUP_KEY ]] || fail 'Setup key cannot be empty.'
    # NB_SETUP_KEY is consumed by the official client; not a command-line argument or file.
    export NB_SETUP_KEY
    netbird up --management-url https://netbird.rusoft54.ru
    unset NB_SETUP_KEY
  fi
fi
unset NB_SETUP_KEY
NB_IP=$(netbird status --ipv4)
NB_IP=$(python3 scripts/prepare.py check-ip "$NB_IP")
ip -j -4 address show | python3 -c 'import json,sys; ip=sys.argv[1]; assert any(a.get("local")==ip for i in json.load(sys.stdin) for a in i.get("addr_info",[])), "NetBird IP not assigned on host"' "$NB_IP"
python3 scripts/prepare.py "$ROOT" "$NB_IP"
if [[ ! -f data/singbox/config.json ]]; then
  if [[ -n ${SINGBOX_CONFIG:-} ]]; then
    cp -- "$SINGBOX_CONFIG" "$tmp/config.json"
  else
    [[ -n ${SINGBOX_URL:-} ]] || prompt SINGBOX_URL 'HTTPS sing-box JSON subscription URL (hidden)'
    [[ $SINGBOX_URL == https://* && $SINGBOX_URL != *[$'\r\n']* ]] || fail 'Subscription must be an HTTPS URL.'
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL --connect-timeout 20 --max-time 120 "$SINGBOX_URL" -o "$tmp/config.json"
    unset SINGBOX_URL
  fi
  python3 scripts/prepare.py check-singbox "$tmp/config.json"
  # Run the actual validator before persisting downloaded configuration.
  image=$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["singbox"]["image"])')
  docker run --rm --network none -v "$tmp/config.json:/candidate.json:ro" "$image" check -c /candidate.json
  install -m 600 "$tmp/config.json" data/singbox/config.json
fi
python3 scripts/prepare.py check-singbox data/singbox/config.json
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps singbox check -c /etc/sing-box/config.json
docker compose up -d singbox cliproxy
# Configure only a fresh profile via the supported CLI, not a copied personal YAML.
if [[ ! -f data/hermes/config.yaml ]]; then
  touch data/hermes/.ai-stack-initializing
fi
if [[ -f data/hermes/.ai-stack-initializing ]]; then
  docker compose run --rm --no-deps -e HERMES_DASHBOARD=0 hermes config set model.provider custom
  docker compose run --rm --no-deps -e HERMES_DASHBOARD=0 hermes config set model.base_url http://cliproxy:8317/v1
  docker compose run --rm --no-deps -e HERMES_DASHBOARD=0 hermes config set model.api_key '${CLIPROXY_KEY}'
  rm data/hermes/.ai-stack-initializing
fi
docker compose up -d
printf '\nServices started (not yet inference-authorized). Dashboard: http://%s:9119\n' "$NB_IP"
printf 'Credentials: %s/.env (root-only). Next: README provider authorization and bin/verify.\n' "$ROOT"
