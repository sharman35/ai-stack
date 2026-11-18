#!/usr/bin/env python3
"""Validate input and create private first-run files, never replace user data."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sys


def valid_ip(value):
    ip = ipaddress.IPv4Address(value)
    if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_link_local or ip == ipaddress.IPv4Address('255.255.255.255'):
        raise ValueError('A non-loopback NetBird IPv4 address is required')
    return str(ip)


def validate_config(path):
    config = json.loads(Path(path).read_text())
    inbounds = config.get('inbounds', [])
    if len(inbounds) != 1 or inbounds[0].get('type') != 'mixed' or inbounds[0].get('listen') != '0.0.0.0' or inbounds[0].get('listen_port') != 2080:
        raise ValueError('Config must contain exactly one mixed inbound on 0.0.0.0:2080 (container only); no TUN')
    if not config.get('outbounds'):
        raise ValueError('Config needs real user-supplied outbounds')
    if config.get('experimental', {}).get('clash_api', {}).get('external_controller'):
        raise ValueError('Disable Clash external_controller')
    return config


def create(path, text):
    path = Path(path)
    if path.exists():
        return
    with path.open('x') as f:
        f.write(text)
    path.chmod(0o600)


def prepare(root, ip):
    ip = valid_ip(ip)
    root = Path(root)
    for sub in ['hermes', 'cliproxy/auths', 'cliproxy/logs', 'singbox/cache']:
        (root / 'data' / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
    env = root / '.env'
    if env.exists():
        values = dict(line.split('=', 1) for line in env.read_text().splitlines() if line and not line.startswith('#'))
        if values.get('NETBIRD_IP') != ip:
            raise ValueError('NetBird IP changed: review and edit .env manually; refusing to overwrite')
        for key in ['CLIPROXY_KEY', 'MANAGEMENT_KEY', 'DASHBOARD_PASSWORD', 'DASHBOARD_SECRET', 'HERMES_API_KEY']:
            if not values.get(key, '').isalnum() or len(values[key]) < 32:
                raise ValueError('Missing/invalid generated secret: ' + key)
    else:
        # Do not silently attach new keys to an unrelated pre-existing deployment.
        if (root / 'data/cliproxy/config.yaml').exists():
            raise ValueError('Existing CLIProxy config without .env: restore matching .env from backup')
        values = {key: secrets.token_hex(32) for key in ['CLIPROXY_KEY', 'MANAGEMENT_KEY', 'DASHBOARD_PASSWORD', 'DASHBOARD_SECRET', 'HERMES_API_KEY']}
        values['NETBIRD_IP'] = ip
        create(env, ''.join(f'{k}={v}\n' for k, v in values.items()))
    create(root / 'data/cliproxy/config.yaml', f'''config-version: 8
server:
  host: "0.0.0.0"
  port: 8317
management:
  allow-remote: true
  secret-key: "{values['MANAGEMENT_KEY']}"
  disable-control-panel: false
access:
  api-keys: ["{values['CLIPROXY_KEY']}"]
oauth:
  auth-dir: /root/.cli-proxy-api
requests:
  proxy-url: "http://singbox:2080"
''')
    return values


if __name__ == '__main__':
    os.umask(0o077)
    if sys.argv[1] == 'check-singbox':
        validate_config(sys.argv[2])
    elif sys.argv[1] == 'check-ip':
        print(valid_ip(sys.argv[2]))
    else:
        prepare(sys.argv[1], sys.argv[2])
