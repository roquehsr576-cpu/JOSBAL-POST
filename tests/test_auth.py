import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

class Authentication(unittest.TestCase):
    def test_protected_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                port=sock.getsockname()[1]
            env={**os.environ,'HOST':'127.0.0.1','JOSBAL_IMPORT_MENU':'0','PORT':str(port),'JOSBAL_DB':str(Path(tmp)/'db'),'JOSBAL_USER':'tester','JOSBAL_PASSWORD':'test-only-long-password'}
            proc=subprocess.Popen([sys.executable,'app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def call(path,auth=None,body=None,extra=None):
                headers={'Content-Type':'application/json',**(extra or {})}
                if auth:
                    headers['Authorization']='Basic '+base64.b64encode(auth.encode()).decode()
                req=Request(f'http://127.0.0.1:{port}'+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
                return urlopen(req,timeout=3)
            try:
                for _ in range(100):
                    try:
                        with call('/api/state','tester:test-only-long-password') as r:
                            self.assertEqual(r.status,200)
                        break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail('El servidor no inició')
                for path in ('/','/app.js','/api/state','/cocina','/barra','/ticket?id=1','/api/production','/api/tickets/1'):
                    with self.assertRaises(HTTPError) as error:
                        call(path)
                    self.assertEqual(error.exception.code,401)
                for path in ('/api/tables','/api/orders','/api/production/status','/api/sales/return-stock'):
                    with self.assertRaises(HTTPError) as error:
                        call(path,body={'name':'Mesa no autorizada'})
                    self.assertEqual(error.exception.code,401)
                    error.exception.close()
                with self.assertRaises(HTTPError) as error:
                    call('/api/state','tester:wrong')
                self.assertEqual(error.exception.code,401)
                with self.assertRaises(HTTPError) as error:
                    call('/api/open','tester:test-only-long-password',{'opening':'0'},{'Sec-Fetch-Site':'cross-site'})
                self.assertEqual(error.exception.code,403)
                with call('/api/open','tester:test-only-long-password',{'opening':'0'}) as r:
                    self.assertIsNotNone(json.load(r)['shift'])
            finally:
                proc.terminate()
                proc.wait(timeout=3)

    def test_network_requires_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            env={**os.environ,'HOST':'0.0.0.0','JOSBAL_USER':'','JOSBAL_PASSWORD':'','JOSBAL_DB':str(Path(tmp)/'db')}
            result=subprocess.run([sys.executable,'app.py'],env=env,capture_output=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'JOSBAL_PASSWORD',result.stderr)
