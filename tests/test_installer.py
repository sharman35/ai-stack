#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT / 'scripts/prepare.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class InstallerTests(unittest.TestCase):
    def test_reject_bad_ips(self):
        for ip in ['', '0.0.0.0', '127.0.0.1', '::', '224.0.0.1', 'x', '100.64.1.1:80']:
            with self.assertRaises(ValueError): p.valid_ip(ip)
        self.assertEqual(p.valid_ip('100.80.10.2'), '100.80.10.2')

    def test_idempotent_secrets_and_user_data(self):
        with tempfile.TemporaryDirectory() as d:
            a = p.prepare(d, '100.80.10.2')
            config = Path(d) / 'data/cliproxy/config.yaml'
            config.write_text('# user managed\n')
            b = p.prepare(d, '100.80.10.2')
            self.assertEqual(a, b)
            self.assertEqual(config.read_text(), '# user managed\n')
            self.assertEqual((Path(d) / '.env').stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(set(a[k] for k in a if k != 'NETBIRD_IP')), 5)
            with self.assertRaises(ValueError): p.prepare(d, '100.80.10.3')

    def test_missing_env_refuses_existing_config(self):
        with tempfile.TemporaryDirectory() as d:
            p.prepare(d, '100.80.10.2')
            (Path(d) / '.env').unlink()
            with self.assertRaises(ValueError): p.prepare(d, '100.80.10.2')

    def test_subscription_validation(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'config.json'
            cfg = {'inbounds': [{'type':'mixed', 'listen':'0.0.0.0','listen_port':2080}], 'outbounds':[{'type':'direct'}]}
            f.write_text(json.dumps(cfg)); p.validate_config(f)
            cfg['inbounds'][0]['type'] = 'tun'
            f.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError): p.validate_config(f)
            f.write_text('not json')
            with self.assertRaises(ValueError): p.validate_config(f)

    def test_compose_real_parser(self):
        compose = os.environ.get('COMPOSE_BIN')
        if not compose: self.skipTest('Set COMPOSE_BIN to standalone Docker Compose executable')
        with tempfile.TemporaryDirectory() as d:
            p.prepare(d, '100.80.10.2')
            cmd = [compose, '--env-file', str(Path(d)/'.env'), '-f', str(ROOT/'docker-compose.yml'), 'config', '--format', 'json']
            cfg = json.loads(subprocess.check_output(cmd))
            for service in cfg['services'].values():
                for port in service.get('ports', []):
                    self.assertEqual(port['host_ip'], '100.80.10.2')
            self.assertTrue(cfg['networks']['private']['internal'])
            self.assertEqual(set(cfg['services']['hermes']['networks']), {'private'})
            self.assertEqual(set(cfg['services']['cliproxy']['networks']), {'private'})
            self.assertFalse(cfg['services']['singbox'].get('ports'))
            (Path(d)/'.env').write_text('')
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)

if __name__ == '__main__': unittest.main(verbosity=2)
