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

class SalesFlow(unittest.TestCase):
    def test_sale_and_closing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as s:
                s.bind(('127.0.0.1',0))
                port=s.getsockname()[1]
            env={k:v for k,v in os.environ.items() if k not in ('HOST','JOSBAL_USER','JOSBAL_PASSWORD')}
            env.update({'PORT':str(port),'JOSBAL_DB':str(Path(tmp)/'test.db')})
            proc=subprocess.Popen([sys.executable,'app.py'],cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def request(path,body=None):
                req=Request(f'http://127.0.0.1:{port}'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
                with urlopen(req,timeout=3) as r:
                    return json.load(r)
            try:
                for _ in range(100):
                    try:
                        state=request('/api/state')
                        break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail('El servidor no inició')
                self.assertEqual(state['products'],[])
                with urlopen(f'http://127.0.0.1:{port}/') as response:
                    self.assertIn('JOSBAL',response.read().decode())
                p=request('/api/products',{'name':'Café','price':'25.50','stock':5})['products'][0]
                sale={'payment':'cash','received':'100','items':[{'id':p['id'],'quantity':2}]}
                with self.assertRaises(HTTPError) as error:
                    request('/api/sales',sale)
                self.assertEqual(error.exception.code,400)
                request('/api/open',{'opening':'200'})
                state=request('/api/sales',sale)
                self.assertEqual(state['receipt'],{'id':1,'total':5100,'change':4900})
                self.assertEqual(state['products'][0]['stock'],3)
                self.assertEqual(state['shift']['expected'],25100)
                with self.assertRaises(HTTPError):
                    request('/api/sales',{'payment':'cash','received':'1000','items':[{'id':p['id'],'quantity':2},{'id':p['id'],'quantity':2}]})
                self.assertEqual(request('/api/state')['products'][0]['stock'],3)
                with self.assertRaises(HTTPError):
                    request('/api/sales',{**sale,'received':'1'})
                state=request('/api/sales',{'payment':'card','items':[{'id':p['id'],'quantity':1}]})
                self.assertEqual(state['shift']['expected'],25100)
                self.assertEqual(state['shift']['total_sales'],7650)
                close=request('/api/close',{'counted':'250'})
                self.assertIsNone(close['shift'])
                self.assertEqual(close['closing']['difference'],-100)
                request('/api/open',{'opening':'50'})
                self.assertEqual(request('/api/state')['shift']['expected'],5000)
                proc.terminate()
                proc.wait(timeout=3)
                proc=subprocess.Popen([sys.executable,'app.py'],cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:
                        state=request('/api/state')
                        break
                    except OSError:
                        time.sleep(.05)
                self.assertEqual(len(state['sales']),2)
                self.assertEqual(state['products'][0]['stock'],2)
            finally:
                proc.terminate()
                proc.wait(timeout=3)
