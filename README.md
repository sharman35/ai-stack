# Clean AI stack

Hermes (official Docker image, gateway **and dashboard**) + CLIProxyAPI + sing-box. NetBird runs **on the host**, enrolled with `https://netbird.rusoft54.ru`. No personal Hermes profile, provider tokens, subscription, or setup key is included. Upstream bundled Hermes skills are still part of its stock image.

**Status:** locally tested configuration generation, Compose parsing, and actual sing-box/CLIProxyAPI binaries. Full Docker/Hermes/NetBird deployment has **not** been exercised. See [TESTING.md](TESTING.md). Installation alone does not provide paid models or prove inference works.

## Requirements and installation

Use a dedicated Debian/Ubuntu host with systemd, root access, Internet access to GitHub/container registries, and sufficient disk/RAM for the official Hermes image. Do not run on a production Docker host without reviewing Docker's firewall/network changes. Installer installs Docker and NetBird if absent; it does not configure SSH or NetBird ACLs.

After this repository is published:

```bash
curl -fsSL https://raw.githubusercontent.com/sharman35/ai-stack/main/install.sh | sudo bash
```

Prefer downloading and reviewing `install.sh` before running as root. It clones into `/opt/ai-stack`; set `INSTALL_DIR` to change this. Existing installations are not git-pulled or overwritten. Docker Compose plugin must be installed if you already have a Docker distribution without it.

The installer prompts through `/dev/tty` (not pipeline stdin) for:

1. A NetBird setup key, hidden. Generate it in your own management console. An already connected peer on this management server is reused; an active peer on another/unknown server is not moved.
2. An HTTPS **sing-box JSON configuration** subscription URL, hidden, unless `data/singbox/config.json` already exists or `SINGBOX_CONFIG=/absolute/path/config.json` was supplied.

For automation, pass `NB_SETUP_KEY` and either `SINGBOX_URL` or `SINGBOX_CONFIG` in the installer's environment; `sudo` normally removes environment variables, so explicitly preserve only the required ones. Never put key values in shell command history, repository files, or Compose. The setup key is passed to NetBird through its supported `NB_SETUP_KEY` environment variable, then unset; it is never saved by this installer. NetBird retains its own enrollment state under host-managed storage.

The subscription must be a full JSON object with **exactly one** inbound:

```json
{"type":"mixed","listen":"0.0.0.0","listen_port":2080}
```

This wildcard is **inside the container only**; port 2080 is never published. Supply your own actual outbounds and routing. TUN configs, Clash YAML, base64 URI lists, and Clash controller listeners are rejected. Subscription configs requiring relative rule-set/certificate files need those files adapted/mounted manually. The installer validates with the real sing-box binary before persisting the initial config. It does not poll or overwrite subscriptions on subsequent runs. Back up and replace config manually to update it, validate it, then restart singbox.

## Access and credentials

Connect your client to the same NetBird deployment. Configure administrator ACLs permitting only trusted peers to host TCP 22 (if SSH is desired), 9119, 8317, and optionally 8642. SSH must already be enabled and key-secured by the host administrator. No public port-forwarding is needed.

| Port on host NetBird IP | Purpose |
|---|---|
| 9119 | Hermes web dashboard / Desktop remote backend; **the UI** |
| 8317 | CLIProxyAPI OpenAI API; management UI at `/management.html` |
| 8642 | Hermes agent OpenAI-compatible API; **not a UI** |

Generated secrets are in `/opt/ai-stack/.env` (mode 0600). Read locally as root, not in shared logs. Dashboard username is `admin`, password `DASHBOARD_PASSWORD`. CLIProxy clients use `CLIPROXY_KEY`; management uses `MANAGEMENT_KEY`; Hermes API clients use `HERMES_API_KEY`. These are independently generated. CLIProxy may hash its management secret in its config on startup; `.env` retains the client value.

HTTP here travels inside NetBird's encrypted tunnel. Do not expose these ports to the Internet. For browser secure-context features or untrusted networks, put a correctly authenticated TLS reverse proxy on the private network. Docker publishes ports only on the verified, locally assigned NetBird IPv4; missing `.env` binding is a hard Compose error.

## Authorize a provider, then select a model

Open `http://NETBIRD_IP:8317/management.html`, authenticate with `MANAGEMENT_KEY`, and configure a provider you own. Follow the upstream provider flow and terms; some OAuth providers need callback forwarding. No callback ports are published automatically.

For Codex device authorization (when supported by your subscription), the upstream binary also supports:

```bash
cd /opt/ai-stack
sudo docker compose exec cliproxy /CLIProxyAPI/CLIProxyAPI -config /CLIProxyAPI/config.yaml -codex-device-login -no-browser -login-proxy http://singbox:2080
```

Use the displayed verification URL/code on your own browser. Tokens persist in `data/cliproxy/auths`. Do not send tokens to the repository maintainer. Other providers may need their own API keys or OAuth flow; use the upstream documentation rather than substituting a random key.

Then run:

```bash
sudo ./bin/verify
sudo docker compose exec hermes hermes config set model.default YOUR_EXACT_MODEL_ID
sudo docker compose restart hermes
sudo docker compose exec hermes hermes chat -q 'Reply with OK'
```

Choose an actual ID from `bin/verify`, not a model guessed from a tutorial. The last command uses your provider allowance and is the inference smoke test. The verifier checks dashboard authentication and API key enforcement without making a billable chat request; empty model discovery exits nonzero. First-run Hermes config points at `http://cliproxy:8317/v1`, uses the custom provider, and references its key from environment. No user model/subscription is assumed. Configure Telegram or other platforms yourself via Hermes dashboard/setup if desired.

## Operations and migration

```bash
cd /opt/ai-stack
sudo docker compose ps
sudo docker compose logs --since 10m
sudo docker compose stop
sudo docker compose up -d
```

Installer reruns preserve `.env`, Hermes data, CLIProxy config/auths, and sing-box config. An interrupted first Hermes configuration is retried using a marker. A changed NetBird IP is refused: review and update `NETBIRD_IP` in `.env` deliberately. Back up before upgrades; `docker compose pull && docker compose up -d` upgrades images. CLIProxy and sing-box defaults are pinned in Compose; Hermes currently uses upstream `latest`, so record a tested digest/tag in `HERMES_VERSION` before reproducible production rollout. Add version overrides to `.env`. Installer reruns pull current configured images.

To migrate:

1. Stop the old stack to get a consistent SQLite backup. Keep it stopped while copying.
2. Securely archive/copy **both `.env` and `data/`** with ownership/modes; these contain secrets. Encrypt backups. Do not copy the running host's unrelated `~/.hermes`.
3. Enroll the new host in NetBird separately; do not clone the old host's NetBird identity.
4. Clone this repo on the new host, restore `.env` and `data/`, deliberately update `NETBIRD_IP`, then run installer with that `INSTALL_DIR`.
5. Run verifier and an authorized chat. Never run two Hermes gateways against one data directory.

To remove the app, `docker compose down` preserves bind-mounted data. Host Docker/NetBird remain installed intentionally. Do not delete data unless you have a verified backup.

## Network and security model

- Hermes and CLIProxy are on an **internal Docker network only**. Only sing-box joins the egress network. Proxy environment/config routes HTTP(S) outbound through sing-box. Programs ignoring proxies fail rather than receiving a direct default route. Docker DNS behavior and host-local reachability are not a complete hostile-code sandbox; this is not a guarantee against every possible DNS/local-network channel.
- No host networking, Docker socket mount, privileged containers, TUN device, or host profile mount. sing-box and CLIProxy drop capabilities. Hermes uses its official root initialization/s6 privilege-drop mechanism, not a custom entrypoint.
- NetBird stays on the host; remote access does not depend on the proxy container. Enrollment and image pulls use host Internet access, not sing-box.
- Dashboard can execute agent tools. Treat dashboard/API credentials like remote shell credentials. Docker group/root access can read environment secrets.
- User-controlled subscription is trusted routing configuration: inspect it for direct routes, unexpected outbound servers, and external rule sets. A `direct` outbound remains direct; installer does not invent or enforce a paid tunnel.
- Setup scripts downloaded from Docker/NetBird and `main` are mutable upstream supply-chain dependencies. Audit/pin them for regulated environments.

## Official references

- [Hermes Docker](https://hermes-agent.nousresearch.com/docs/user-guide/docker)
- [Hermes dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) and its versioned config example
- [sing-box](https://sing-box.sagernet.org/)
- [NetBird self-hosted client setup](https://docs.netbird.io/)
