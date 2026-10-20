import base64
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

class MenuImport(unittest.TestCase):
    def test_migration_public_menu_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/'db'
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,price INTEGER NOT NULL CHECK(price>0),stock INTEGER NOT NULL CHECK(stock>=0))')
                db.execute("INSERT INTO products VALUES(1,'Producto existente',1234,7)")
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                port=sock.getsockname()[1]
            env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'JOSBAL_DB':str(dbpath),'JOSBAL_IMPORT_MENU':'1','JOSBAL_USER':'tester','JOSBAL_PASSWORD':'test-only-long-password'}
            auth='Basic '+base64.b64encode(b'tester:test-only-long-password').decode()
            def call(path,body=None,private=False):
                headers={'Content-Type':'application/json'}
                if private: headers['Authorization']=auth
                with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers=headers,data=json.dumps(body).encode() if body is not None else None),timeout=3) as r:
                    return r.read()
            def start():
                proc=subprocess.Popen([sys.executable,'app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:
                        call('/api/menu')
                        return proc
                    except OSError:
                        time.sleep(.05)
                proc.terminate();proc.wait(timeout=3)
                self.fail('El servidor no inició')
            proc=start()
            try:
                menu=json.loads(call('/api/menu'))['items']
                self.assertEqual(len(menu),157)
                self.assertEqual(len({p['category'] for p in menu}),26)
                self.assertEqual(next(p for p in menu if p['name']=='Papas gajo')['price'],8000)
                self.assertNotIn('Cambio a papas gajo',[p['name'] for p in menu])
                self.assertTrue(all(set(p)=={'name','price','category','description'} for p in menu))
                self.assertNotIn('Producto existente',[p['name'] for p in menu])
                page=call('/menu')
                self.assertIn(b'JOSBAL',page)
                self.assertIn(b'/food-images.js',page)
                self.assertIn(b'Im',page)
                self.assertTrue(call('/images/menu-photos.png').startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertIn(b'background-size:400% 700%',call('/food-images.css'))
                self.assertIn(b'Alitas',call('/food-images.js'))
                self.assertIn('Imágenes individuales del menú'.encode(),call('/imagenes'))
                self.assertTrue(call('/images/products/01-chilaquiles-rojos-con-huevo-v1.png').startswith(b'\x89PNG\r\n\x1a\n'))
                # Downloads are real ZIP files generated from the same image allowlist.
                import io,zipfile
                with zipfile.ZipFile(io.BytesIO(call('/imagenes/descargar?lote=1'))) as archive:
                    self.assertEqual(sum(name.endswith('.png') for name in archive.namelist()),10)
                    self.assertIsNone(archive.testzip())
                self.assertTrue(call('/menu.pdf').startswith(b'%PDF'))
                with self.assertRaises(HTTPError) as error:call('/api/state')
                self.assertEqual(error.exception.code,401);error.exception.close()
                state=json.loads(call('/api/state',private=True))
                original=next(p for p in state['products'] if p['id']==1)
                self.assertEqual((original['price'],original['stock'],original['inventory_managed']),(1234,7,1))
                p=next(p for p in state['products'] if p['name']=='Americano · Grande')
                self.assertEqual(p['price'],4000)
                call('/api/open',{'opening':'0'},True)
                sale=json.loads(call('/api/sales',{'payment':'card','items':[{'id':p['id'],'quantity':2,'notes':'Media carga'}]},True))
                self.assertEqual(sale['receipt']['total'],8000)
                call('/api/products',{'id':p['id'],'name':p['name'],'price':'42','stock':0,'category':p['category'],'description':p['description'],'inventory_managed':0,'preparation_profile':'none'},True)
                proc.terminate();proc.wait(timeout=3)
                proc=start()
                state=json.loads(call('/api/state',private=True))
                self.assertEqual(len(state['products']),159)
                p=next(row for row in state['products'] if row['name']=='Americano · Grande')
                self.assertEqual(p['price'],4200)
                self.assertEqual(p['preparation_profile'],'none')
                self.assertEqual(len(state['sales']),1)
                self.assertEqual(state['sales'][0]['items'][0]['notes'],'Media carga')
                coffee_tickets=json.loads(call('/api/production',private=True))['tickets']
                self.assertTrue(any(i['notes']=='Media carga' for t in coffee_tickets for i in t['items']))
                burger=next(p for p in state['products'] if p['name']=='Hamburguesa clásica con papas')
                note='Sin cebolla, Cambiar a papas gajo (+$7)'
                table=json.loads(call('/api/tables',{'name':'Mesa gajo'},True))['tables'][0]['id']
                lines=[{'id':burger['id'],'quantity':2,'notes':note},{'id':burger['id'],'quantity':1,'notes':''}]
                saved=json.loads(call('/api/orders',{'table_id':table,'items':lines},True))
                pending=next(o for o in saved['orders'] if o['table_id']==table)
                self.assertEqual(pending['items'][0]['notes'],note)
                tickets=json.loads(call('/api/production',private=True))['tickets']
                self.assertTrue(any(i['notes']==note for t in tickets for i in t['items']))
                paid=json.loads(call('/api/sales',{'table_id':table,'order_revision':pending['revision'],'payment':'cash','received':'1000','items':lines},True))
                expected=burger['price']*3+1400
                self.assertEqual(paid['receipt']['total'],expected)
                self.assertEqual(paid['receipt']['change'],100000-expected)
                sold=next(s for s in paid['sales'] if s['id']==paid['receipt']['id'])
                self.assertEqual([i['price'] for i in sold['items']],[burger['price']+700,burger['price']])
                with self.assertRaises(HTTPError) as error:
                    call('/api/sales',{'payment':'card','items':[{'id':p['id'],'quantity':1,'notes':note}]},True)
                self.assertEqual(error.exception.code,400);error.exception.close()

                self.assertEqual(state['products'][0]['inventory_managed'],0)
            finally:
                proc.terminate();proc.wait(timeout=3)
