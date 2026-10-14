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

class AdjustmentsFlow(unittest.TestCase):
    def test_changes_and_cancellations_require_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={k:v for k,v in os.environ.items() if k not in ('JOSBAL_USER','JOSBAL_PASSWORD')}
            env.update(HOST='127.0.0.1',PORT=str(port),JOSBAL_DB=str(Path(tmp)/'db'),JOSBAL_IMPORT_MENU='0')
            def call(path,body=None):
                with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers={'Content-Type':'application/json'},data=json.dumps(body).encode() if body else None),timeout=3) as r:
                    return json.load(r)
            def rejected(path,body):
                with self.assertRaises(HTTPError) as error:call(path,body)
                self.assertEqual(error.exception.code,400);error.exception.close()
            proc=subprocess.Popen([sys.executable,'app.py'],cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:call('/api/state');break
                    except OSError:time.sleep(.05)
                else:self.fail('No inició')
                call('/api/open',{'opening':'100'})
                tid=call('/api/tables',{'name':'Mesa 1'})['tables'][0]['id']
                state=call('/api/products',{'name':'Hamburguesa','price':'80','stock':5,'category':'Hamburguesas'})
                burger=state['products'][0]['id']
                state=call('/api/products',{'name':'Latte','price':'45','stock':5,'category':'Bebidas calientes'})
                latte=next(p['id'] for p in state['products'] if p['name']=='Latte')
                self.assertIn('Cliente cambió de opinión',state['reasons'])

                state=call('/api/orders',{'table_id':tid,'items':[{'id':burger,'quantity':2,'notes':''},{'id':latte,'quantity':1,'notes':''}]})
                order=state['orders'][0]
                # Adding products needs no reason.
                state=call('/api/orders',{'table_id':tid,'order_revision':order['revision'],'items':[{'id':burger,'quantity':2,'notes':''},{'id':latte,'quantity':2,'notes':''}]})
                order=state['orders'][0]
                self.assertEqual(state['adjustments'],[])
                swap={'table_id':tid,'order_revision':order['revision'],'items':[{'id':burger,'quantity':1,'notes':''},{'id':burger,'quantity':1,'notes':'Sin cebolla'},{'id':latte,'quantity':2,'notes':''}]}
                rejected('/api/orders',swap)
                rejected('/api/orders',{**swap,'reason':'Otro'})
                state=call('/api/orders',{**swap,'reason':'Error al tomar el pedido','reason_notes':'Era sin cebolla'})
                change=state['adjustments'][0]
                self.assertEqual((change['kind'],change['reason'],change['notes'],change['amount']),('change','Error al tomar el pedido','Era sin cebolla',8000))
                self.assertEqual(change['items'],[{'id':burger,'name':'Hamburguesa','quantity':1,'price':8000,'notes':''}])

                order=state['orders'][0]
                rejected('/api/orders/cancel',{'table_id':tid,'order_revision':order['revision']})
                state=call('/api/orders/cancel',{'table_id':tid,'order_revision':order['revision'],'reason':'Demora en el servicio'})
                self.assertEqual(state['orders'],[])
                self.assertEqual(state['adjustments'][0]['kind'],'cancel_order')
                self.assertEqual(state['adjustments'][0]['amount'],8000*2+4500*2)
                kitchen=[t for t in call('/api/production')['tickets'] if t['station']=='kitchen']
                self.assertEqual(kitchen[-1]['items'],[])

                state=call('/api/sales',{'payment':'cash','received':'200','items':[{'id':burger,'quantity':2,'notes':''}]})
                sale=state['sales'][0]
                self.assertEqual(state['products'][0]['stock'],3)
                self.assertEqual(state['shift']['expected'],26000)
                rejected('/api/sales/cancel',{'id':sale['id']})
                state=call('/api/sales/cancel',{'id':sale['id'],'reason':'Problema de calidad','reason_notes':'Carne cruda'})
                self.assertEqual(state['sales'][0]['cancel_reason'],'Problema de calidad')
                self.assertEqual(next(p for p in state['products'] if p['id']==burger)['stock'],5)
                self.assertEqual((state['shift']['expected'],state['shift']['total_sales'],state['shift']['cancelled_sales']),(10000,0,16000))
                self.assertEqual(state['adjustments'][0]['sale_id'],sale['id'])
                rejected('/api/sales/cancel',{'id':sale['id'],'reason':'Otro','reason_notes':'Otra vez'})
                self.assertEqual(call('/api/close',{'counted':'100'})['closing']['difference'],0)
                call('/api/open',{'opening':'0'})
                state=call('/api/sales',{'payment':'card','items':[{'id':latte,'quantity':1,'notes':''}]})
                call('/api/close',{'counted':'0'})
                rejected('/api/sales/cancel',{'id':state['sales'][0]['id'],'reason':'Producto agotado'})
            finally:
                proc.terminate();proc.wait(timeout=3)

if __name__=='__main__':
    unittest.main()
