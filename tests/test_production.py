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

class ProductionFlow(unittest.TestCase):
    def test_split_orders_status_changes_and_payment(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={k:v for k,v in os.environ.items() if k not in ('JOSBAL_USER','JOSBAL_PASSWORD')}
            env.update(HOST='127.0.0.1',PORT=str(port),JOSBAL_DB=str(Path(tmp)/'db'),JOSBAL_IMPORT_MENU='0')
            def raw(path,body=None):
                with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers={'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None),timeout=3) as r:return r.read()
            def call(path,body=None):return json.loads(raw(path,body))
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
                table=call('/api/tables',{'name':'Mesa 3'})['tables'][0]['id']
                food=call('/api/products',{'name':'Hamburguesa','category':'Hamburguesas','price':'80','stock':10})['products'][0]['id']
                products=call('/api/products',{'name':'Frappé','category':'Frappés','price':'60','stock':10})['products']
                drink=next(p['id'] for p in products if p['name']=='Frappé')
                call('/api/open',{'opening':'0'})
                order={'table_id':table,'items':[{'id':food,'quantity':1,'notes':'Sin cebolla'},{'id':drink,'quantity':1,'notes':'Sin crema batida'}]}
                state=call('/api/orders',order)
                production_id=state['orders'][0]['production_order_id']
                revision=state['orders'][0]['revision']
                tickets=call('/api/production')['tickets']
                self.assertEqual(len(tickets),2)
                kitchen=next(t for t in tickets if t['station']=='kitchen')
                bar=next(t for t in tickets if t['station']=='bar')
                self.assertEqual(kitchen['order_id'],bar['order_id'])
                self.assertEqual(kitchen['table_name'],'Mesa 3')
                self.assertEqual([p['name'] for p in kitchen['items']],['Hamburguesa'])
                self.assertEqual(bar['items'][0]['notes'],'Sin crema batida')
                self.assertEqual(call('/api/tickets/'+str(kitchen['id']))['station'],'kitchen')
                for page in ['/cocina','/barra','/ticket?id='+str(bar['id'])]:self.assertIn(b'JOSBAL',raw(page))
                state=call('/api/production/status',{'id':bar['id'],'revision':bar['revision'],'status':'ready'})
                newbar=next(t for t in state['tickets'] if t['station']=='bar')
                rejected('/api/production/status',{'id':bar['id'],'revision':bar['revision'],'status':'preparing'})
                # Saving an unchanged order does not create more tickets or reset ready status.
                state=call('/api/orders',{**order,'order_revision':revision})
                revision=state['orders'][0]['revision']
                tickets=call('/api/production')['tickets']
                self.assertEqual(len(tickets),2)
                self.assertEqual(next(t for t in tickets if t['station']=='bar')['status'],'ready')
                # Only the changed area is reopened, with previous contents retained for review.
                order['items'][0]['notes']='Sin mostaza'
                state=call('/api/orders',{**order,'order_revision':revision})
                revision=state['orders'][0]['revision']
                tickets=call('/api/production')['tickets']
                kitchen2=next(t for t in tickets if t['station']=='kitchen')
                self.assertEqual(kitchen2['changes']['previous'][0]['notes'],'Sin cebolla')
                self.assertEqual(kitchen2['items'][0]['notes'],'Sin mostaza')
                self.assertEqual(next(t for t in tickets if t['station']=='bar')['revision'],newbar['revision'])
                # Restart keeps the split tickets, instructions and independent states.
                proc.terminate();proc.wait(timeout=3);proc=start()
                self.assertEqual(call('/api/tickets/'+str(bar['id']))['status'],'ready')
                state=call('/api/sales',{**order,'order_revision':revision,'payment':'card'})
                self.assertEqual(state['receipt']['total'],14000)
                self.assertEqual(state['sales'][0]['production_order_id'],production_id)
                self.assertEqual(len(call('/api/production')['tickets']),2)
                self.assertEqual(call('/api/tickets/'+str(bar['id']))['status'],'ready')
                # A drink-only counter sale creates just one bar ticket.
                call('/api/sales',{'payment':'card','items':[{'id':drink,'quantity':1}]})
                tickets=call('/api/production')['tickets']
                self.assertEqual(len(tickets),3)
                self.assertEqual(tickets[-1]['station'],'bar')
                self.assertEqual(tickets[-1]['table_name'],'Mostrador / para llevar')
                # Product destination can be explicitly overridden.
                call('/api/products',{'id':drink,'name':'Frappé','category':'Frappés','price':'60','stock':8,'production_station':'kitchen'})
                state=call('/api/orders',{'table_id':table,'items':[{'id':drink,'quantity':1}]})
                pid=state['orders'][0]['production_order_id']
                routed=call('/api/production?pedido='+str(pid))['tickets']
                self.assertEqual(len(routed),1)
                self.assertEqual(routed[0]['station'],'kitchen')
                self.assertEqual(call('/api/menu')['items'],[])
            finally:
                proc.terminate();proc.wait(timeout=3)
