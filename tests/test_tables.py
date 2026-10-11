import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

class TablesFlow(unittest.TestCase):
    def test_pending_orders_payment_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={k:v for k,v in os.environ.items() if k not in ('JOSBAL_USER','JOSBAL_PASSWORD')}
            env.update(HOST='127.0.0.1',PORT=str(port),JOSBAL_DB=str(Path(tmp)/'db'),JOSBAL_IMPORT_MENU='0')
            def call(path,body=None):
                with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers={'Content-Type':'application/json'},data=json.dumps(body).encode() if body else None),timeout=3) as r:
                    return json.load(r)
            def start():
                proc=subprocess.Popen([sys.executable,'app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:call('/api/state');return proc
                    except OSError:time.sleep(.05)
                proc.terminate();proc.wait(timeout=3);self.fail('No inició')
            def rejected(path,body):
                with self.assertRaises(HTTPError) as error:call(path,body)
                self.assertEqual(error.exception.code,400);error.exception.close()
            proc=start()
            try:
                state=call('/api/tables',{'name':'Mesa 1'})
                tid=state['tables'][0]['id']
                rejected('/api/tables',{'name':'mesa 1'})
                rejected('/api/tables',{'name':' '})
                call('/api/tables',{'name':'Terraza 2'})
                state=call('/api/products',{'name':'Hamburguesa','price':'80','stock':4})
                pid=state['products'][0]['id']
                call('/api/open',{'opening':'100'})
                order={'table_id':tid,'items':[{'id':pid,'quantity':1,'notes':'Sin cebolla'},{'id':pid,'quantity':1,'notes':'Sin mostaza'}]}
                state=call('/api/orders',order)
                revision=state['orders'][0]['revision']
                self.assertEqual(state['products'][0]['stock'],4)
                self.assertEqual(state['sales'],[])
                self.assertEqual(state['shift']['total_sales'],0)
                rejected('/api/orders',order)
                rejected('/api/tables',{'id':tid,'name':'Mesa 1','active':0})
                proc.terminate();proc.wait(timeout=3);proc=start()
                state=call('/api/state')
                self.assertEqual(state['orders'][0]['items'][0]['notes'],'Sin cebolla')
                updated=call('/api/orders',{**order,'order_revision':revision})
                new_revision=updated['orders'][0]['revision']
                self.assertNotEqual(revision,new_revision)
                sale={**order,'payment':'cash','received':'200','order_revision':revision}
                rejected('/api/sales',sale)
                state=call('/api/sales',{**sale,'order_revision':new_revision})
                self.assertEqual(state['orders'],[])
                self.assertEqual(state['receipt']['total'],16000)
                self.assertEqual(state['products'][0]['stock'],2)
                self.assertEqual(state['sales'][0]['table_name'],'Mesa 1')
                self.assertEqual(state['sales'][0]['items'][1]['notes'],'Sin mostaza')
                rejected('/api/sales',{**sale,'order_revision':new_revision})
                recreated=call('/api/orders',order)
                self.assertNotEqual(recreated['orders'][0]['revision'],new_revision)
                rejected('/api/sales',{**sale,'order_revision':new_revision})
                state=call('/api/sales',{**sale,'order_revision':recreated['orders'][0]['revision']})
                call('/api/tables',{'id':tid,'name':'Jardín','active':0})
                state=call('/api/state')
                self.assertEqual(state['sales'][0]['table_name'],'Mesa 1')
                rejected('/api/orders',order)
                rejected('/api/sales',{**order,'payment':'card'})
            finally:
                proc.terminate();proc.wait(timeout=3)
