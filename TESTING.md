# Verification record

## Executed locally

- `bash -n install.sh`: passed.
- `COMPOSE_BIN=/tmp/ai-stack-test/compose python3 -m unittest discover -s tests -p 'test_*.py' -v`: **5 passed**, no skips (Compose v5.8.0 standalone executable).
- `SINGBOX_BIN=/tmp/ai-stack-test/sing-box-1.14.4-linux-amd64/sing-box CLIPROXY_BIN=/tmp/ai-stack-test/cli-proxy-api python3 tests/native_smoke.py`: passed against actual upstream Linux binaries, not mocked responses.

Unit tests exercise generated secret permissions/uniqueness, idempotent preservation of user configuration, refusal to regenerate keys against existing config, changed-IP refusal, invalid address/config rejection, real Compose parsing, every published host-IP binding, internal network assignments, absence of sing-box published ports, and fail-closed missing environment.

Native smoke runs `sing-box check` on a temporary direct-only fixture (not a shipped production configuration). It boots CLIProxyAPI v8.0.77 using generated config with only its listener and auth storage redirected to temporary loopback/storage; observes actual HTTP 401 without key and HTTP 200 with generated key, with an empty provider model list. Process is terminated and temporary state removed. No production credential is used.

## Not verified

There is no Docker daemon on the development host. No host networking, Docker installation, NetBird enrollment, SSH/ACL configuration, or production CT was changed. No remote infrastructure was used.

Therefore image pulls/architecture availability, Docker bridge forwarding, end-to-end proxy egress, Hermes s6/dashboard boot and provider config interpolation, live dashboard authentication, NetBird installer/enrollment and reboot ordering remain deployment acceptance tests, **not claimed passes**. Native binaries passing does not prove their images will boot together. Provider OAuth and actual model inference require the user's credentials/subscription and were not attempted.

On a dedicated target: run installer, inspect `docker compose ps` and logs, run `sudo ./bin/verify` after authorizing a provider, then a user-approved chat. From a separate NetBird client confirm all intended ports work; from a non-NetBird interface confirm none are reachable. Reboot and repeat. Inspect container routes and perform proxy egress tests with your own subscription before calling this production-ready.

## Upstream references consulted

Official Hermes documentation index and source pages `website/docs/user-guide/docker.md` and `website/docs/user-guide/features/web-dashboard.md`; upstream CLIProxyAPI Dockerfile/config example and actual 8.0.77 executable; upstream NetBird `client/cmd/root.go` confirms the `NB_` flag-environment prefix including setup key. Defaults: sing-box 1.14.4, CLIProxyAPI v8.0.77, Hermes latest (mutable; pin after runtime acceptance).
