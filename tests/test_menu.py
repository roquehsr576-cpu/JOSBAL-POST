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
                self.assertEqual(len(menu),158)
                self.assertEqual(len({p['category'] for p in menu}),27)
                self.assertTrue(all(set(p)=={'name','price','category','description'} for p in menu))
                self.assertNotIn('Producto existente',[p['name'] for p in menu])
                page=call('/menu')
                self.assertIn(b'JOSBAL',page)
                self.assertIn(b'/food-images.js',page)
                self.assertIn(b'Im',page)
                self.assertTrue(call('/images/menu-photos.png').startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertIn(b'background-size:400% 700%',call('/food-images.css'))
                self.assertIn(b'Alitas',call('/food-images.js'))
                self.assertTrue(call('/menu.pdf').startswith(b'%PDF'))
                with self.assertRaises(HTTPError) as error:call('/api/state')
                self.assertEqual(error.exception.code,401);error.exception.close()
                state=json.loads(call('/api/state',private=True))
                original=next(p for p in state['products'] if p['id']==1)
                self.assertEqual((original['price'],original['stock'],original['inventory_managed']),(1234,7,1))
                p=next(p for p in state['products'] if p['name']=='Americano · Grande')
                self.assertEqual(p['price'],4000)
                call('/api/open',{'opening':'0'},True)
                sale=json.loads(call('/api/sales',{'payment':'card','items':[{'id':p['id'],'quantity':2}]},True))
                self.assertEqual(sale['receipt']['total'],8000)
                call('/api/products',{'id':p['id'],'name':p['name'],'price':'42','stock':0,'category':p['category'],'description':p['description'],'inventory_managed':0},True)
                proc.terminate();proc.wait(timeout=3)
                proc=start()
                state=json.loads(call('/api/state',private=True))
                self.assertEqual(len(state['products']),159)
                p=next(row for row in state['products'] if row['name']=='Americano · Grande')
                self.assertEqual(p['price'],4200)
                self.assertEqual(len(state['sales']),1)
                self.assertEqual(state['products'][0]['inventory_managed'],0)
            finally:
                proc.terminate();proc.wait(timeout=3)
