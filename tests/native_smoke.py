#!/usr/bin/env python3
"""Exercise downloaded upstream binaries without Docker or host network changes."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', root/'scripts/prepare.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]

with tempfile.TemporaryDirectory() as d:
    d = Path(d); env = p.prepare(d, '100.80.10.2')
    cfg = {'inbounds':[{'type':'mixed','listen':'0.0.0.0','listen_port':2080}], 'outbounds':[{'type':'direct'}]}
    f = d/'sing.json'; f.write_text(json.dumps(cfg))
    subprocess.run([os.environ['SINGBOX_BIN'], 'check', '-c', str(f)], check=True)
    # Native smoke binds loopback only. Never run a public listener for tests.
    httpport = port()
    config = d/'data/cliproxy/config.yaml'
    text = config.read_text().replace('0.0.0.0','127.0.0.1').replace('port: 8317',f'port: {httpport}').replace('/root/.cli-proxy-api', str(d/'data/cliproxy/auths')).replace('disable-control-panel: false','disable-control-panel: true')
    config.write_text(text)
    with (d/'log').open('w') as log:
        proc = subprocess.Popen([os.environ['CLIPROXY_BIN'], '-config', str(config)], cwd=d, stdout=log, stderr=log)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{httpport}/v1/models'
            for _ in range(100):
                try:
                    opener.open(url, timeout=1)
                except urllib.error.HTTPError as e:
                    assert e.code == 401; break
                except OSError:
                    if proc.poll() is not None: raise RuntimeError((d/'log').read_text())
                    time.sleep(.1)
                else: raise AssertionError('Unauthenticated models request accepted')
            else: raise AssertionError('CLIProxy never became ready')
            req = urllib.request.Request(url, headers={'Authorization':'Bearer '+env['CLIPROXY_KEY']})
            result = json.load(opener.open(req, timeout=5))
            assert result['data'] == [], result
            print('PASS: sing-box real config validator; CLIProxy generated v8 config boots, rejects missing key (401), accepts generated key (200), zero provider credentials.')
        finally:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
