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
from urllib.request import Request,urlopen
from urllib.error import HTTPError

class AccountPermissions(unittest.TestCase):
    def test_roles_sessions_revocation_and_private_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'JOSBAL_DB':str(Path(tmp)/'db'),'JOSBAL_IMPORT_MENU':'0','JOSBAL_USER':'owner','JOSBAL_PASSWORD':'test-only-owner-password'}
            admin='Basic '+base64.b64encode(b'owner:test-only-owner-password').decode()
            proc=subprocess.Popen([sys.executable,'app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def request(path,body=None,cookie=None,basic=None):
                headers={'Content-Type':'application/json'}
                if cookie:headers['Cookie']=cookie
                if basic:headers['Authorization']=basic
                with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers=headers,data=json.dumps(body).encode() if body is not None else None),timeout=5) as r:
                    raw=r.read()
                    return (json.loads(raw) if raw and r.headers.get('Content-Type','').startswith('application/json') else raw,r.headers)
            def denied(path,body=None,cookie=None,code=403):
                with self.assertRaises(HTTPError) as error:request(path,body,cookie)
                self.assertEqual(error.exception.code,code);error.exception.close()
            try:
                for _ in range(100):
                    try:request('/api/state',basic=admin);break
                    except OSError:time.sleep(.05)
                else:self.fail('No inició')
                for user,role in [('server','waiter'),('cashier','cashier')]:
                    request('/api/users',{'username':user,'password':'test-only-employee-password','role':role},basic=admin)
                denied('/api/login',{'username':'server','password':'wrong'},code=401)
                _,headers=request('/api/login',{'username':'server','password':'test-only-employee-password'})
                waiter=headers['Set-Cookie'].split(';')[0]
                self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
                self.assertEqual(request('/api/state',cookie=waiter)[0]['current_user']['role'],'waiter')
                request('/api/open',{'opening':'100'},basic=admin)
                table=request('/api/tables',{'name':'Mesa 1'},basic=admin)[0]['tables'][0]['id']
                product=request('/api/products',{'name':'Café','price':'30','stock':10},basic=admin)[0]['products'][0]['id']
                for path in ['/api/users','/api/backups','/api/audit']:denied(path,cookie=waiter)
                for path in ['/api/open','/api/close','/api/sales','/api/products','/api/tables','/api/orders/cancel','/api/sales/cancel','/api/sales/return-stock']:
                    denied(path,{},waiter)
                data=request('/api/orders',{'table_id':table,'items':[{'id':product,'quantity':1}]},waiter)[0]
                self.assertEqual(len(data['orders']),1)
                self.assertNotIn('cash_sales',data['shift']);self.assertEqual(data['sales'],[])
                _,headers=request('/api/login',{'username':'cashier','password':'test-only-employee-password'})
                cashier=headers['Set-Cookie'].split(';')[0]
                sale=request('/api/sales',{'payment':'cash','received':'30','items':[{'id':product,'quantity':1}]},cashier)[0]
                self.assertEqual(sale['receipt']['total'],3000)
                denied('/api/sales/cancel',{'id':sale['receipt']['id'],'reason':'Error al tomar el pedido'},cashier)
                backup=request('/api/backups',{},basic=admin)[0]['backups'][0]['name']
                raw=request('/api/backups/'+backup,basic=admin)[0]
                self.assertTrue(raw.startswith(b'SQLite format 3'))
                denied('/api/backups/'+backup,cookie=waiter)
                events=request('/api/audit',basic=admin)[0]['events']
                self.assertTrue(any(e['username']=='cashier' and e['action']=='/api/sales' for e in events))
                users=request('/api/users',basic=admin)[0]['users']
                self.assertFalse(any('password_hash' in u for u in users))
                uid=next(u['id'] for u in users if u['username']=='server')
                request('/api/users',{'id':uid,'username':'server','role':'waiter','active':0},basic=admin)
                denied('/api/state',cookie=waiter,code=401)
                with self.assertRaises(HTTPError) as revoked:
                    request('/api/state',cookie=waiter,basic=admin)
                self.assertEqual(revoked.exception.code,401);revoked.exception.close()
                request('/api/logout',{},cashier)
                denied('/api/state',cookie=cashier,code=401)
                denied('/api/state',cookie='josbal_session=loggedout',code=401)
                self.assertEqual(request('/api/menu')[0]['items'],[])
                self.assertIn(b'JOSBAL',request('/login')[0])
            finally:proc.terminate();proc.wait(timeout=5)
