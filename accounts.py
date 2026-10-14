import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import threading
from collections import defaultdict

FAILURES=defaultdict(list)
AUTH_LOCK=threading.Lock()

ROLES=('admin','cashier','waiter')

def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE COLLATE NOCASE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),bootstrap INTEGER NOT NULL DEFAULT 0,expires INTEGER NOT NULL);''')

def password_hash(password):
    if not isinstance(password,str) or len(password)<16 or len(password)>200:
        raise ValueError('La contraseña debe tener entre 16 y 200 caracteres.')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return f'{salt}:{digest}'

def check_password(password,stored):
    salt,digest=stored.split(':')
    value=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return hmac.compare_digest(value,digest)

def bootstrap_user():
    username=os.environ.get('JOSBAL_USER','')
    return {'id':0,'username':username,'role':'admin','active':1,'bootstrap':True} if username else None

def authenticate(db,username,password):
    key=username.casefold()
    with AUTH_LOCK:
        timestamp=time.monotonic()
        FAILURES[key]=[t for t in FAILURES[key] if timestamp-t<60]
        if len(FAILURES[key])>=10:return None
    bootstrap=bootstrap_user()
    if bootstrap and hmac.compare_digest(username.encode(),bootstrap['username'].encode()) and hmac.compare_digest(password.encode(),os.environ.get('JOSBAL_PASSWORD','').encode()):
        with AUTH_LOCK:FAILURES.pop(key,None)
        return bootstrap
    row=db.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
    if row and check_password(password,row['password_hash']):
        with AUTH_LOCK:FAILURES.pop(key,None)
        return {field:row[field] for field in ('id','username','role','active')}
    with AUTH_LOCK:
        if len(FAILURES)>10000:FAILURES.clear()
        FAILURES[key].append(time.monotonic())
    return None

def users(db):
    rows=[dict(r) for r in db.execute('SELECT id,username,role,active FROM users ORDER BY id')]
    bootstrap=bootstrap_user()
    return ([bootstrap] if bootstrap else [])+rows

def session_user(db,token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',(digest,int(time.time()))).fetchone()
    if not row:return None
    if row['bootstrap']:return bootstrap_user()
    user=db.execute('SELECT id,username,role,active FROM users WHERE id=? AND active=1',(row['user_id'],)).fetchone()
    return dict(user) if user else None

def create_session(db,user):
    token=secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires<=?',(int(time.time()),))
    db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'] or None,1 if user.get('bootstrap') else 0,int(time.time())+43200))
    return token

def save_user(db,body):
    username=body.get('username','')
    if not isinstance(username,str) or not username.strip() or len(username)>60 or ':' in username:
        raise ValueError('Escribe un usuario de hasta 60 caracteres, sin dos puntos.')
    username=username.strip()
    if username.casefold()==os.environ.get('JOSBAL_USER','').casefold():
        raise ValueError('El administrador principal se configura en Render y no puede modificarse aquí.')
    role=body.get('role')
    if role not in ROLES:raise ValueError('Selecciona un rol válido.')
    active=0 if str(body.get('active','1'))=='0' else 1
    uid=int(body['id']) if body.get('id') else None
    if uid and not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ValueError('Usuario no encontrado.')
    if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?',(username,uid or 0)).fetchone():raise ValueError('Ese usuario ya existe.')
    hashed=password_hash(body['password']) if body.get('password') else None
    if uid:
        if not bootstrap_user() and (not active or role!='admin'):
            others=db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1 AND id!=?",(uid,)).fetchone()[0]
            current=db.execute('SELECT role,active FROM users WHERE id=?',(uid,)).fetchone()
            if current['role']=='admin' and current['active'] and not others:raise ValueError('Debe quedar al menos un administrador activo.')
        db.execute('UPDATE users SET username=?,role=?,active=?,password_hash=coalesce(?,password_hash) WHERE id=?',(username,role,active,hashed,uid))
        db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    else:
        if not bootstrap_user() and not db.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone() and (role!='admin' or not active):
            raise ValueError('La primera cuenta debe ser un administrador activo.')
        if not hashed:raise ValueError('Introduce una contraseña para el usuario nuevo.')
        db.execute('INSERT INTO users(username,password_hash,role,active) VALUES(?,?,?,?)',(username,hashed,role,active))

POST_ROLES={
 '/api/products':('admin',),'/api/tables':('admin',),'/api/tables/remove':('admin',),
 '/api/open':('admin','cashier'),'/api/close':('admin','cashier'),'/api/sales':('admin','cashier'),
 '/api/orders':ROLES,'/api/production/status':('admin','cashier'),
 '/api/orders/cancel':('admin',),'/api/sales/cancel':('admin',),'/api/sales/return-stock':('admin',),
 '/api/users':('admin',),'/api/backups':('admin',)}
