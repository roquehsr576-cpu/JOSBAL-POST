import json
import base64
from product_pricing import unit_price
import hmac
import uuid
import os
import hashlib
import tempfile
import zipfile
import shutil
from http.cookies import SimpleCookie
import sqlite3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from datetime import datetime, timezone
import accounts
from backups import Backups
from production import send_tickets, tickets, cancel_tickets
from adjustments import REASONS, reason_from, removed_lines, log_adjustment, adjustments

ROOT = Path(__file__).parent
DB = Path(os.environ.get('JOSBAL_DB', ROOT / 'data' / 'josbal.sqlite3'))
DB.parent.mkdir(parents=True, exist_ok=True)
BACKUPS = Backups(DB,os.environ.get('JOSBAL_BACKUP_DIR'))
if DB.exists() and DB.stat().st_size:
    BACKUPS.create('pre-upgrade')

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

with connect() as db:
    accounts.initialize(db)
    db.execute('DELETE FROM sessions WHERE bootstrap=1')
    db.execute('CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT NOT NULL,username TEXT NOT NULL,role TEXT NOT NULL,action TEXT NOT NULL)')
    had_inventory_returns = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_returns'").fetchone() is not None
    db.executescript('''
    CREATE TABLE IF NOT EXISTS ready_events(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL,order_id INTEGER NOT NULL,station TEXT NOT NULL,table_name TEXT NOT NULL,created TEXT NOT NULL,all_ready INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS production_orders(id INTEGER PRIMARY KEY AUTOINCREMENT,table_name TEXT NOT NULL,created TEXT NOT NULL,sale_id INTEGER REFERENCES sales(id));
    CREATE TABLE IF NOT EXISTS production_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL REFERENCES production_orders(id),station TEXT NOT NULL,items TEXT NOT NULL,changes TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'pending',updated TEXT NOT NULL,revision TEXT NOT NULL,UNIQUE(order_id,station));
    CREATE TABLE IF NOT EXISTS dining_tables(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS table_orders(table_id INTEGER PRIMARY KEY REFERENCES dining_tables(id), items TEXT NOT NULL, updated TEXT NOT NULL, revision TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>0), stock INTEGER NOT NULL CHECK(stock>=0));
    CREATE TABLE IF NOT EXISTS shifts(id INTEGER PRIMARY KEY, opened TEXT NOT NULL, opening INTEGER NOT NULL, closed TEXT, counted INTEGER);
    CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL REFERENCES shifts(id), created TEXT NOT NULL, total INTEGER NOT NULL, payment TEXT NOT NULL, received INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS inventory_returns(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_id INTEGER NOT NULL REFERENCES sales(id),product_id INTEGER NOT NULL REFERENCES products(id),quantity INTEGER NOT NULL CHECK(quantity>0),created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS adjustments(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT NOT NULL,kind TEXT NOT NULL,reason TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',items TEXT NOT NULL,amount INTEGER NOT NULL,table_name TEXT NOT NULL DEFAULT '',sale_id INTEGER REFERENCES sales(id),production_order_id INTEGER REFERENCES production_orders(id));
    CREATE TABLE IF NOT EXISTS items(sale_id INTEGER REFERENCES sales(id), product_id INTEGER REFERENCES products(id), name TEXT NOT NULL, quantity INTEGER NOT NULL, price INTEGER NOT NULL);
    ''')
    # Additive migration preserves existing products, inventory and sales.
    columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
    for name, definition in [('category', "TEXT NOT NULL DEFAULT ''"), ('description', "TEXT NOT NULL DEFAULT ''"), ('inventory_managed', 'INTEGER NOT NULL DEFAULT 1'), ('menu_key', 'TEXT'), ('preparation_profile', "TEXT NOT NULL DEFAULT 'auto'"), ('production_station', "TEXT NOT NULL DEFAULT 'auto'"), ('prep_minutes', 'INTEGER NOT NULL DEFAULT 0'), ('show_in_menu', 'INTEGER NOT NULL DEFAULT 1'), ('custom_options', "TEXT NOT NULL DEFAULT '[]'")]:
        if name not in columns:
            db.execute(f'ALTER TABLE products ADD COLUMN {name} {definition}')
    if 'retired' not in columns:
        db.execute('ALTER TABLE products ADD COLUMN retired INTEGER NOT NULL DEFAULT 0')
        # Retire only the duplicate explicitly identified by its name and stock.
        # Keep its ID and historical records available for existing orders and sales.
        duplicates = db.execute("SELECT id FROM products WHERE lower(name) IN ('hamburguesa clásica','hamburguesa clasica') AND menu_key IS NULL AND inventory_managed=1 AND stock=100").fetchall()
        official = db.execute("SELECT 1 FROM products WHERE menu_key IS NOT NULL AND name='Hamburguesa clásica'").fetchone()
        if len(duplicates)==1 and official:
            db.execute('UPDATE products SET retired=1 WHERE id=?',(duplicates[0]['id'],))
    if 'notes' not in {r['name'] for r in db.execute('PRAGMA table_info(items)')}:
        db.execute("ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if 'inventory_managed_at_sale' not in {r['name'] for r in db.execute('PRAGMA table_info(items)')}:
        db.execute('ALTER TABLE items ADD COLUMN inventory_managed_at_sale INTEGER')
    if 'removed' not in {r['name'] for r in db.execute('PRAGMA table_info(dining_tables)')}:
        db.execute('ALTER TABLE dining_tables ADD COLUMN removed INTEGER NOT NULL DEFAULT 0')
    sales_columns = {r['name'] for r in db.execute('PRAGMA table_info(sales)')}
    if 'table_id' not in sales_columns:
        db.execute('ALTER TABLE sales ADD COLUMN table_id INTEGER REFERENCES dining_tables(id)')
    if 'table_name' not in sales_columns:
        db.execute("ALTER TABLE sales ADD COLUMN table_name TEXT NOT NULL DEFAULT ''")
    for name, definition in [('archived_at','TEXT'),('archived_by',"TEXT NOT NULL DEFAULT ''"),('cancelled', 'TEXT'), ('cancel_reason', "TEXT NOT NULL DEFAULT ''"), ('cancel_notes', "TEXT NOT NULL DEFAULT ''")]:
        if name not in sales_columns:
            db.execute(f'ALTER TABLE sales ADD COLUMN {name} {definition}')
    for table_name in ('sales','table_orders'):
        if 'production_order_id' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table_name})')}:
            db.execute(f'ALTER TABLE {table_name} ADD COLUMN production_order_id INTEGER REFERENCES production_orders(id)')
    if not had_inventory_returns:
        # Old cancellations already restored stock automatically. Mark those units as returned.
        db.execute('''INSERT INTO inventory_returns(sale_id,product_id,quantity,created)
            SELECT s.id,i.product_id,sum(i.quantity),s.cancelled FROM sales s JOIN items i ON i.sale_id=s.id
            WHERE s.cancelled IS NOT NULL GROUP BY s.id,i.product_id''')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS products_menu_key ON products(menu_key)')
    if os.environ.get('JOSBAL_IMPORT_MENU', '1') == '1':
        menu = json.loads((ROOT / 'catalog' / 'menu.json').read_text())
        for item in menu['items']:
            db.execute('INSERT OR IGNORE INTO products(name,price,stock,category,description,inventory_managed,menu_key) VALUES(?,?,0,?,?,0,?)', (item['name'],item['price'],item['category'],item['description'],item['key']))


    # One-time correction: the standalone side and burger substitution are distinct.
    db.execute('CREATE TABLE IF NOT EXISTS app_migrations(name TEXT PRIMARY KEY)')
    if not db.execute("SELECT 1 FROM app_migrations WHERE name='gajo-side-and-burger-option-v1'").fetchone():
        db.execute("UPDATE products SET price=8000 WHERE menu_key='pdf-v1-020' OR name='Papas gajo'")
        db.execute("UPDATE products SET retired=1 WHERE menu_key='pdf-v1-036' OR name='Cambio a papas gajo'")
        db.execute("UPDATE products SET description=replace(description,'Por $5 más, cambia a papas gajo.','Por $7 más, cambia a papas gajo.') WHERE category='Hamburguesas con papas'")
        db.execute("INSERT INTO app_migrations VALUES('gajo-side-and-burger-option-v1')")

def money(value):
    from decimal import Decimal, InvalidOperation
    try:
        n = Decimal(str(value)) * 100
        if not n.is_finite() or n < 0 or n != n.to_integral_value() or n > 100000000:
            raise ValueError('Importe inválido (máximo dos decimales).')
        return int(n)
    except InvalidOperation:
        raise ValueError('Importe inválido.')

def integer(value):
    if isinstance(value, bool) or str(value) != str(int(value)) or int(value) < 0:
        raise ValueError('Cantidad inválida.')
    return int(value)

def now():
    return datetime.now(timezone.utc).isoformat()

def sale_history(db,archived=False,before=9223372036854775807):
    condition='archived_at IS NOT NULL' if archived else 'archived_at IS NULL'
    sales=[dict(r) for r in db.execute(f'SELECT * FROM sales WHERE {condition} AND id<? ORDER BY id DESC LIMIT 30',(before,))]
    for sale in sales:
        sale['returnable_items'] = [dict(r) for r in db.execute('''
            SELECT p.id,p.name,sum(i.quantity) - coalesce((SELECT sum(quantity) FROM inventory_returns WHERE sale_id=? AND product_id=p.id),0) AS remaining
            FROM items i JOIN products p ON p.id=i.product_id
            WHERE i.sale_id=? AND coalesce(i.inventory_managed_at_sale,p.inventory_managed)=1 AND p.inventory_managed=1
            GROUP BY p.id HAVING remaining>0''',(sale['id'],sale['id']))]
        sale['items'] = [dict(r) for r in db.execute('SELECT product_id,name,quantity,price,notes FROM items WHERE sale_id=? ORDER BY rowid', (sale['id'],))]
    return sales

def snapshot(db):
    shift = db.execute('SELECT * FROM shifts WHERE closed IS NULL ORDER BY id DESC LIMIT 1').fetchone()
    sales=sale_history(db)
    result = dict(shift) if shift else None
    if result:
        result['cash_sales'] = db.execute("SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND payment='cash' AND cancelled IS NULL", (shift['id'],)).fetchone()[0]
        result['total_sales'] = db.execute('SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND cancelled IS NULL', (shift['id'],)).fetchone()[0]
        result['cancelled_sales'] = db.execute('SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND cancelled IS NOT NULL', (shift['id'],)).fetchone()[0]
        result['expected'] = result['opening'] + result['cash_sales']
    tables = [dict(r) for r in db.execute('SELECT * FROM dining_tables WHERE removed=0 ORDER BY id')]
    orders = [dict(r) for r in db.execute('SELECT * FROM table_orders ORDER BY table_id')]
    for order in orders:
        order['items'] = json.loads(order['items'])
    return {'tables': tables, 'orders': orders, 'products': [dict(r) for r in db.execute('SELECT * FROM products ORDER BY name')], 'shift': result, 'sales': sales, 'adjustments': adjustments(db), 'reasons': list(REASONS)}

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'public, max-age=604800' if self.path.startswith('/images/products/') else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()

    def authorized(self):
        self.user = None
        with connect() as db:
            token=''
            cookie=SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie',''))
                token=cookie['josbal_session'].value if 'josbal_session' in cookie else ''
                if token:self.user=accounts.session_user(db,token)
            except Exception:
                pass
            if not self.user and not token:
                try:
                    method,encoded=self.headers.get('Authorization','').split(' ',1)
                    username,password=base64.b64decode(encoded,validate=True).decode().split(':',1)
                    if method=='Basic':self.user=accounts.authenticate(db,username,password)
                except (ValueError,UnicodeError):
                    pass
            if not self.user and not token and not os.environ.get('JOSBAL_USER') and not os.environ.get('JOSBAL_PASSWORD') and os.environ.get('HOST','127.0.0.1')=='127.0.0.1' and not db.execute('SELECT 1 FROM users WHERE active=1').fetchone():
                self.user={'id':0,'username':'Local','role':'admin','active':1,'local':True}
        if self.user:return True
        if self.command=='GET' and urlsplit(self.path).path in ('/','/cocina','/barra','/ticket'):
            self.send_response(303)
            self.send_header('Location','/login?next='+quote(self.path,safe=''))
            self.send_header('Content-Length','0');self.end_headers()
            return False
        self.send_response(401)
        if not token:self.send_header('WWW-Authenticate','Basic realm="JOSBAL", charset="UTF-8"')
        raw=json.dumps({'error':'Tu sesión terminó o no has iniciado sesión. Entra nuevamente en /login.'}).encode()
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
        return False

    def forbidden(self):
        self.reply(403,{'error':'Tu cuenta no tiene permiso para esta acción. Solicita apoyo del administrador.'})

    def state(self,db):
        data=snapshot(db)
        data['current_user']=self.user
        if self.user['role']!='admin':data['adjustments']=[]
        if self.user['role']=='waiter':
            data['sales']=[]
            data['shift']={k:v for k,v in data['shift'].items() if k in ('id','opened')} if data['shift'] else None
        return data

    def session_cookie(self,token):
        secure='; Secure' if os.environ.get('HOST','127.0.0.1')!='127.0.0.1' else ''
        self.send_header('Set-Cookie',f'josbal_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={43200 if token else 0}{secure}')

    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path in ('/login','/login.js','/login.css'):
            name={'/login':'login.html','/login.js':'login.js','/login.css':'login.css'}[urlsplit(self.path).path]
            raw=(ROOT/'static'/name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]])
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            return
        if self.path == '/api/menu':
            with connect() as db:
                rows = db.execute('SELECT name,price,category,description FROM products WHERE menu_key IS NOT NULL AND retired=0 AND show_in_menu=1 ORDER BY menu_key')
                self.reply(200, {'currency':'MXN', 'items':[dict(r) for r in rows]})
            return
        public = {'/menu': 'menu.html', '/menu/': 'menu.html', '/menu.js': 'menu.js', '/product-groups.js': 'product-groups.js', '/menu.css': 'menu.css', '/menu.pdf': 'menu.pdf', '/food-images.js': 'food-images.js', '/food-images.css': 'food-images.css', '/images/menu-photos.png': 'images/menu-photos.png'}
        image_manifest=ROOT/'catalog/product-images.json'
        if image_manifest.exists():
            public.update({item['url']:item['url'].lstrip('/') for item in json.loads(image_manifest.read_text())})
        public['/imagenes']='image-gallery.html'
        public['/imagenes/lote-01.zip']='images/josbal-lote-01.zip'
        if urlsplit(self.path).path=='/imagenes/descargar':
            try:
                batch=integer(parse_qs(urlsplit(self.path).query).get('lote',['0'])[0])
                groups=json.loads((ROOT/'catalog/image-batches.json').read_text())
                if not 1<=batch<=len(groups):raise ValueError('Lote no encontrado.')
                with tempfile.SpooledTemporaryFile(max_size=8*1024*1024) as output:
                    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as archive:
                        for url in groups[batch-1]:
                            relative=public.get(url)
                            if not relative:raise ValueError('Imagen no disponible.')
                            archive.write(ROOT/'static'/relative,Path(relative).name)
                    length=output.tell();output.seek(0)
                    self.send_response(200);self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition',f'attachment; filename="josbal-lote-{batch:02}.zip"')
                    self.send_header('Content-Length',str(length));self.end_headers()
                    shutil.copyfileobj(output,self.wfile,length=65536)
            except (ValueError,IndexError):self.reply(404,{'error':'Lote no encontrado.'})
            return
        if self.path in public:
            file = ROOT / 'static' / public[self.path]
            raw = file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.pdf':'application/pdf','.png':'image/png','.zip':'application/zip'}[file.suffix])
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if not self.authorized():
            return
        if self.path in ('/api/users','/api/backups','/api/audit') or self.path.startswith('/api/backups/'):
            if self.user['role']!='admin':self.forbidden();return
            if self.path=='/api/users':
                with connect() as db:self.reply(200,{'users':accounts.users(db)})
            elif self.path=='/api/audit':
                with connect() as db:self.reply(200,{'events':[dict(r) for r in db.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 200')]})
            elif self.path=='/api/backups':
                self.reply(200,{'backups':BACKUPS.listing(),'error':BACKUPS.error,'interval_hours':6,'retained':14})
            else:
                try:
                    path=BACKUPS.file(self.path.rsplit('/',1)[1])
                    raw=path.read_bytes();self.send_response(200)
                    self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition',f'attachment; filename="{path.name}"')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except ValueError:self.reply(404,{'error':'Respaldo no encontrado.'})
            return
        if urlsplit(self.path).path == '/api/sales-history':
            if self.user['role']=='waiter':self.forbidden();return
            try:
                params=parse_qs(urlsplit(self.path).query)
                archived=params.get('archived',['0'])[0]=='1'
                before=integer(params['before'][0]) if 'before' in params else 9223372036854775807
                with connect() as db:
                    rows=sale_history(db,archived,before)
                    self.reply(200,{'sales':rows,'next':rows[-1]['id'] if len(rows)==30 else None})
            except (ValueError,OverflowError):self.reply(400,{'error':'Consulta de historial inválida.'})
            return
        if urlsplit(self.path).path == '/api/ready-events':
            try:
                params=parse_qs(urlsplit(self.path).query)
                with connect() as db:
                    latest=db.execute('SELECT coalesce(max(id),0) FROM ready_events').fetchone()[0]
                    if 'after' not in params:
                        self.reply(200,{'events':[],'cursor':latest})
                    else:
                        after=integer(params['after'][0])
                        events=[dict(r) for r in db.execute('SELECT * FROM ready_events WHERE id>? ORDER BY id LIMIT 50',(after,))]
                        self.reply(200,{'events':events,'cursor':events[-1]['id'] if events else latest})
            except ValueError:self.reply(400,{'error':'Consulta de avisos inválida.'})
            return
        if urlsplit(self.path).path == '/api/production':
            try:
                order_filter = parse_qs(urlsplit(self.path).query).get('pedido',[None])[0]
                order_id = integer(order_filter) if order_filter is not None else None
                with connect() as db:
                    self.reply(200, {'tickets': tickets(db,order_id)})
            except ValueError:
                self.reply(400, {'error':'Número de comanda inválido.'})
            return
        if self.path.startswith('/api/tickets/'):
            try:
                ticket_id = integer(self.path.rsplit('/',1)[1])
                with connect() as db:
                    row = db.execute('SELECT order_id FROM production_tickets WHERE id=?',(ticket_id,)).fetchone()
                    ticket = next((t for t in tickets(db,row['order_id']) if t['id']==ticket_id),None) if row else None
                    self.reply(200 if ticket else 404,ticket or {'error':'Comanda no encontrada.'})
            except ValueError:
                self.reply(400,{'error':'Comanda inválida.'})
            return
        if self.path == '/api/state':
            with connect() as db:
                self.reply(200, self.state(db))
            return
        files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/ready-alerts.js':'ready-alerts.js', '/preparation-options.js': 'preparation-options.js', '/cocina':'production.html', '/barra':'production.html', '/production.js':'production.js', '/production.css':'production.css', '/ticket':'ticket.html', '/ticket.js':'ticket.js'}
        page = self.path.split('?',1)[0]
        if page not in files:
            self.reply(404, {'error': 'No encontrado'})
            return
        file = ROOT / 'static' / files[page]
        raw = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[file.suffix[1:]])
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path == '/api/login':
            if self.headers.get('Sec-Fetch-Site')=='cross-site' or self.headers.get('Content-Type','').split(';')[0]!='application/json':self.reply(403,{'error':'Solicitud no permitida.'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:raise ValueError('Solicitud inválida.')
                body=json.loads(self.rfile.read(length))
                username,password=body.get('username',''),body.get('password','')
                if not isinstance(username,str) or not isinstance(password,str) or len(password)>200:raise ValueError('Datos inválidos.')
                with connect() as db:
                    user=accounts.authenticate(db,username,password)
                    if not user:self.reply(401,{'error':'Usuario o contraseña incorrectos.'});return
                    token=accounts.create_session(db,user)
                raw=json.dumps({'user':user}).encode();self.send_response(200);self.session_cookie(token)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            except (ValueError,TypeError):self.reply(400,{'error':'Datos inválidos.'})
            return
        if not self.authorized():
            return
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.reply(403, {'error': 'Solicitud no permitida.'})
            return
        if self.path=='/api/logout':
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            if 'josbal_session' in cookie:
                with connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(cookie['josbal_session'].value.encode()).hexdigest(),))
            self.send_response(200);self.session_cookie('loggedout');self.send_header('Content-Length','0');self.end_headers();return
        if self.user['role'] not in accounts.POST_ROLES.get(self.path,('admin',)):
            self.forbidden();return
        if self.path=='/api/backups':
            try:BACKUPS.create();self.reply(200,{'backups':BACKUPS.listing(),'error':None})
            except Exception:self.reply(500,{'error':BACKUPS.error})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 65536:
                raise ValueError('Solicitud demasiado grande.')
            body = json.loads(self.rfile.read(length))
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                shift = db.execute('SELECT * FROM shifts WHERE closed IS NULL').fetchone()
                extra = {}
                db.execute('INSERT INTO audit_log(created,username,role,action) VALUES(?,?,?,?)',(now(),self.user['username'],self.user['role'],self.path))
                if self.path == '/api/sales/archive':
                    if not isinstance(body.get('ids'),list) or not 1<=len(body['ids'])<=1000:
                        raise ValueError('Selecciona de 1 a 1000 ventas.')
                    ids=sorted({integer(value) for value in body['ids']})
                    archive=body.get('archive')
                    if not isinstance(archive,bool):raise ValueError('Acción de archivo inválida.')
                    marks=','.join('?' for _ in ids)
                    found=db.execute(f'SELECT count(*) FROM sales WHERE id IN ({marks})',ids).fetchone()[0]
                    if found!=len(ids):raise ValueError('Alguna venta no existe. Actualiza el historial.')
                    db.execute(f'UPDATE sales SET archived_at=?,archived_by=? WHERE id IN ({marks})',(now() if archive else None,self.user['username'] if archive else '',*ids))
                    db.execute('INSERT INTO audit_log(created,username,role,action) VALUES(?,?,?,?)',(now(),self.user['username'],self.user['role'],('archive:' if archive else 'restore:')+','.join(map(str,ids))))
                elif self.path == '/api/users':
                    accounts.save_user(db,body)
                    db.commit();self.reply(200,{'users':accounts.users(db)});return
                elif self.path == '/api/production/status':
                    status = body.get('status')
                    if status not in ('pending','preparing','ready'):
                        raise ValueError('Estado de comanda inválido.')
                    ticket_id = integer(body['id'])
                    previous=db.execute('SELECT * FROM production_tickets WHERE id=?',(ticket_id,)).fetchone()
                    if db.execute('UPDATE production_tickets SET status=?,revision=? WHERE id=? AND revision=?',(status,uuid.uuid4().hex,ticket_id,str(body.get('revision','')))).rowcount != 1:
                        raise ValueError('La comanda cambió. Actualiza la pantalla antes de marcarla.')
                    if status=='ready' and previous['status']!='ready' and json.loads(previous['items']):
                        order=db.execute('SELECT * FROM production_orders WHERE id=?',(previous['order_id'],)).fetchone()
                        relevant=[r for r in db.execute('SELECT status,items FROM production_tickets WHERE order_id=?',(previous['order_id'],)) if json.loads(r['items'])]
                        all_ready=all(r['status']=='ready' for r in relevant)
                        db.execute('INSERT INTO ready_events(ticket_id,order_id,station,table_name,created,all_ready) VALUES(?,?,?,?,?,?)',(ticket_id,previous['order_id'],previous['station'],order['table_name'],now(),int(all_ready)))
                    db.commit()
                    self.reply(200, {'tickets':tickets(db)})
                    return
                elif self.path == '/api/tables/remove':
                    table_id = integer(body['id'])
                    if db.execute('SELECT 1 FROM table_orders WHERE table_id=?',(table_id,)).fetchone():
                        raise ValueError('Esta mesa tiene un pedido pendiente. Abre Ver pedido y cancélalo con su motivo antes de quitar la mesa.')
                    if db.execute('UPDATE dining_tables SET removed=1,active=0 WHERE id=? AND removed=0',(table_id,)).rowcount != 1:
                        raise ValueError('Mesa no encontrada.')
                elif self.path == '/api/tables':
                    name = body.get('name', '')
                    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                        raise ValueError('Escribe un nombre de mesa de hasta 60 caracteres.')
                    name = name.strip()
                    tid = integer(body['id']) if body.get('id') else None
                    active = 0 if str(body.get('active', '1')) == '0' else 1
                    if tid and not active and db.execute('SELECT 1 FROM table_orders WHERE table_id=?',(tid,)).fetchone():
                        raise ValueError('Cobra el pedido pendiente antes de desactivar la mesa.')
                    archived = db.execute('SELECT id FROM dining_tables WHERE name=? COLLATE NOCASE AND removed=1',(name,)).fetchone()
                    if not tid and archived:
                        tid = archived['id']
                    if db.execute('SELECT 1 FROM dining_tables WHERE name=? COLLATE NOCASE AND id!=?',(name,tid or 0)).fetchone():
                        raise ValueError('Ya existe una mesa con ese nombre.')
                    if tid:
                        if db.execute('UPDATE dining_tables SET name=?,active=?,removed=0 WHERE id=?',(name,active,tid)).rowcount != 1:
                            raise ValueError('Mesa no encontrada.')
                    else:
                        db.execute('INSERT INTO dining_tables(name,active) VALUES(?,?)',(name,active))
                elif self.path == '/api/products':
                    name = str(body['name']).strip()
                    price, stock = money(body['price']), integer(body['stock'])
                    if not name or len(name) > 120 or price <= 0:
                        raise ValueError('Introduce un nombre y un precio mayor que cero.')
                    category = str(body.get('category', '')).strip()[:80]
                    description = str(body.get('description', '')).strip()[:2000]
                    managed = 0 if str(body.get('inventory_managed', '1')) == '0' else 1
                    profile = body.get('preparation_profile', 'auto')
                    if profile not in ('auto','burger','hotdog','frappe','tea','cold_drink','none'):
                        raise ValueError('Selecciona un grupo de opciones de preparación válido.')
                    station = body.get('production_station', 'auto')
                    if station not in ('auto','kitchen','bar'):
                        raise ValueError('Selecciona Cocina o Barra como área de preparación.')
                    existing_product = db.execute('SELECT prep_minutes,menu_key,show_in_menu,custom_options FROM products WHERE id=?',(integer(body['id']),)).fetchone() if body.get('id') else None
                    custom_options = existing_product['custom_options'] if existing_product else '[]'
                    if 'custom_options' in body:
                        options = body['custom_options']
                        if isinstance(options,str):
                            options = options.splitlines()
                        if not isinstance(options,list) or len(options)>30:
                            raise ValueError('Añade como máximo 30 opciones, una por línea.')
                        clean,seen = [],set()
                        for option in options:
                            if not isinstance(option,str):
                                raise ValueError('Cada opción debe ser texto.')
                            option = option.strip()
                            if not option:continue
                            if len(option)>80 or ',' in option or '\n' in option or '\r' in option:
                                raise ValueError('Cada opción debe tener hasta 80 caracteres, sin comas ni saltos de línea.')
                            if option in ('Carga completa','Media carga','Cambiar a papas gajo (+$7)'):
                                raise ValueError('Esa opción ya se configura automáticamente en su producto correspondiente.')
                            if option.casefold() not in seen:
                                clean.append(option);seen.add(option.casefold())
                        custom_options = json.dumps(clean,ensure_ascii=False)
                    menu_key = existing_product['menu_key'] if existing_product else None
                    show_in_menu = existing_product['show_in_menu'] if existing_product else 1
                    if 'show_in_menu' in body:
                        visibility = str(body['show_in_menu'])
                        if visibility not in ('0','1'):
                            raise ValueError('Selecciona si el producto aparece en el menú.')
                        show_in_menu = int(visibility)
                        if visibility=='1' and not menu_key:
                            menu_key = 'custom-'+uuid.uuid4().hex
                    prep_minutes = integer(body.get('prep_minutes',existing_product['prep_minutes'] if existing_product else 0))
                    if prep_minutes>1440:
                        raise ValueError('El tiempo estimado debe estar entre 0 y 1440 minutos.')
                    if body.get('id'):
                        if db.execute('UPDATE products SET name=?,price=?,stock=?,category=?,description=?,inventory_managed=?,preparation_profile=?,production_station=?,prep_minutes=?,menu_key=?,show_in_menu=?,custom_options=? WHERE id=?', (name,price,stock,category,description,managed,profile,station,prep_minutes,menu_key,show_in_menu,custom_options,integer(body['id']))).rowcount != 1:
                            raise ValueError('Producto no encontrado.')
                    else:
                        db.execute('INSERT INTO products(name,price,stock,category,description,inventory_managed,preparation_profile,production_station,prep_minutes,menu_key,show_in_menu,custom_options) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(name,price,stock,category,description,managed,profile,station,prep_minutes,menu_key,show_in_menu,custom_options))
                elif self.path == '/api/open':
                    if shift:
                        raise ValueError('La caja ya está abierta.')
                    db.execute('INSERT INTO shifts(opened,opening) VALUES(?,?)',(now(),money(body['opening'])))
                elif self.path == '/api/close':
                    if not shift:
                        raise ValueError('La caja está cerrada.')
                    counted = money(body['counted'])
                    expected = shift['opening'] + db.execute("SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND payment='cash' AND cancelled IS NULL",(shift['id'],)).fetchone()[0]
                    db.execute('UPDATE shifts SET closed=?,counted=? WHERE id=?',(now(),counted,shift['id']))
                    extra = {'closing': {'expected': expected, 'counted': counted, 'difference': counted-expected}}
                elif self.path == '/api/orders/cancel':
                    table_id = integer(body['table_id'])
                    pending = db.execute('SELECT o.*,t.name FROM table_orders o JOIN dining_tables t ON t.id=o.table_id WHERE o.table_id=?',(table_id,)).fetchone()
                    if not pending:
                        raise ValueError('Esta mesa no tiene un pedido pendiente.')
                    if pending['revision'] != str(body.get('order_revision', '')):
                        raise ValueError('El pedido cambió desde otro dispositivo. Recarga la página y vuelve a abrir la mesa.')
                    reason, notes = reason_from(body)
                    log_adjustment(db,'cancel_order',reason,notes,json.loads(pending['items']),now(),pending['name'],pending['production_order_id'])
                    if pending['production_order_id']:
                        cancel_tickets(db,pending['production_order_id'],now())
                    db.execute('DELETE FROM table_orders WHERE table_id=?',(table_id,))
                elif self.path == '/api/sales/cancel':
                    sale = db.execute('SELECT * FROM sales WHERE id=?',(integer(body['id']),)).fetchone()
                    if not sale:
                        raise ValueError('Venta no encontrada.')
                    if sale['cancelled']:
                        raise ValueError('Esta venta ya fue cancelada.')
                    if not shift or sale['shift_id'] != shift['id']:
                        raise ValueError('Solo se pueden cancelar ventas del turno de caja abierto.')
                    reason, notes = reason_from(body)
                    sold = [dict(r) for r in db.execute('SELECT product_id AS id,name,quantity,price,notes FROM items WHERE sale_id=? ORDER BY rowid',(sale['id'],))]
                    db.execute('UPDATE sales SET cancelled=?,cancel_reason=?,cancel_notes=? WHERE id=?',(now(),reason,notes,sale['id']))
                    if sale['production_order_id']:
                        cancel_tickets(db,sale['production_order_id'],now())
                    log_adjustment(db,'cancel_sale',reason,notes,sold,now(),sale['table_name'] or 'Mostrador / para llevar',sale['production_order_id'],sale['id'],sale['total'])
                elif self.path == '/api/sales/return-stock':
                    sale_id = integer(body['id'])
                    sale = db.execute('SELECT * FROM sales WHERE id=?',(sale_id,)).fetchone()
                    if not sale or not sale['cancelled']:
                        raise ValueError('Solo puedes devolver inventario de una venta cancelada.')
                    reason, notes = reason_from(body)
                    quantities = {}
                    for line in body['items']:
                        pid, qty = integer(line['id']), integer(line['quantity'])
                        if qty<=0:
                            raise ValueError('Selecciona una cantidad mayor que cero para devolver.')
                        quantities[pid] = quantities.get(pid,0)+qty
                    if not quantities:
                        raise ValueError('Selecciona las unidades recuperables que realmente regresan al inventario.')
                    returned = []
                    for pid, qty in quantities.items():
                        product = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                        sold_qty = db.execute('SELECT coalesce(sum(quantity),0) FROM items WHERE sale_id=? AND product_id=? AND coalesce(inventory_managed_at_sale,?)=1',(sale_id,pid,product['inventory_managed'] if product else 0)).fetchone()[0]
                        returned_qty = db.execute('SELECT coalesce(sum(quantity),0) FROM inventory_returns WHERE sale_id=? AND product_id=?',(sale_id,pid)).fetchone()[0]
                        if not product or not product['inventory_managed'] or qty>sold_qty-returned_qty:
                            raise ValueError('La cantidad supera las unidades disponibles para devolver o el producto no controla existencias.')
                        db.execute('INSERT INTO inventory_returns(sale_id,product_id,quantity,created) VALUES(?,?,?,?)',(sale_id,pid,qty,now()))
                        db.execute('UPDATE products SET stock=stock+? WHERE id=?',(qty,pid))
                        returned.append({'id':pid,'quantity':qty})
                    log_adjustment(db,'return_stock',reason,notes,returned,now(),sale['table_name'] or 'Mostrador / para llevar',sale['production_order_id'],sale_id,0)
                elif self.path in ('/api/sales', '/api/orders'):
                    saving_order = self.path == '/api/orders'
                    if not saving_order and not shift:
                        raise ValueError('Abre la caja antes de cobrar.')
                    table_id = integer(body['table_id']) if body.get('table_id') else None
                    table = db.execute('SELECT * FROM dining_tables WHERE id=? AND active=1 AND removed=0',(table_id,)).fetchone() if table_id else None
                    if table_id and not table:
                        raise ValueError('Selecciona una mesa activa.')
                    if saving_order and not table:
                        raise ValueError('Selecciona la mesa para guardar el pedido.')
                    pending = db.execute('SELECT * FROM table_orders WHERE table_id=?',(table_id,)).fetchone() if table else None
                    revision = str(body.get('order_revision', '') or '')
                    if (pending and pending['revision'] != revision) or (not pending and revision):
                        raise ValueError('El pedido cambió desde otro dispositivo. Recarga la página y vuelve a abrir la mesa.')
                    payment = body.get('payment', 'cash')
                    if not saving_order and payment not in ('cash','card'):
                        raise ValueError('Método de pago inválido.')
                    quantities = {}
                    order_lines = []
                    for item in body['items']:
                        pid, qty = integer(item['id']), integer(item['quantity'])
                        if qty == 0:
                            raise ValueError('La cantidad debe ser mayor que cero.')
                        notes = item.get('notes', '')
                        if not isinstance(notes, str) or len(notes) > 500:
                            raise ValueError('Las indicaciones deben ser texto de hasta 500 caracteres.')
                        quantities[pid] = quantities.get(pid, 0) + qty
                        order_lines.append((pid, qty, notes.strip()))
                    if not quantities:
                        raise ValueError('Agrega productos a la venta.')
                    rows, total = [], 0
                    for pid, qty in quantities.items():
                        p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                        if not p or (p['inventory_managed'] and p['stock'] < qty):
                            raise ValueError('Stock insuficiente. Actualiza la venta.')
                        rows.append((p,qty))
                    products_by_id = {p['id']:p for p, qty in rows}
                    total = sum(unit_price(products_by_id[pid],notes)*qty for pid,qty,notes in order_lines)
                    production_id = pending['production_order_id'] if pending else None
                    removed = removed_lines(json.loads(pending['items']),[{'id':pid,'quantity':qty,'notes':notes} for pid,qty,notes in order_lines]) if pending else []
                    if removed:
                        reason, reason_notes = reason_from(body)
                        log_adjustment(db,'change',reason,reason_notes,removed,now(),table['name'],production_id)
                    if saving_order:
                        production_id = send_tickets(db,order_lines,table['name'],now(),production_id)
                        clean_items = [{'id':pid,'quantity':qty,'notes':notes} for pid,qty,notes in order_lines]
                        db.execute('INSERT INTO table_orders(table_id,items,updated,revision) VALUES(?,?,?,?) ON CONFLICT(table_id) DO UPDATE SET items=excluded.items,updated=excluded.updated,revision=excluded.revision',(table_id,json.dumps(clean_items,ensure_ascii=False),now(),uuid.uuid4().hex))
                        db.execute('UPDATE table_orders SET production_order_id=? WHERE table_id=?',(production_id,table_id))
                        db.commit()
                        self.reply(200, self.state(db))
                        return
                    received = money(body.get('received',0)) if payment == 'cash' else total
                    if received < total:
                        raise ValueError('El efectivo recibido es insuficiente.')
                    sid = db.execute('INSERT INTO sales(shift_id,created,total,payment,received) VALUES(?,?,?,?,?)',(shift['id'],now(),total,payment,received)).lastrowid
                    production_id = send_tickets(db,order_lines,table['name'] if table else 'Mostrador / para llevar',now(),production_id,sid)
                    db.execute('UPDATE sales SET production_order_id=? WHERE id=?',(production_id,sid))
                    db.execute('UPDATE sales SET table_id=?,table_name=? WHERE id=?',(table_id,table['name'] if table else '',sid))
                    if pending:
                        db.execute('DELETE FROM table_orders WHERE table_id=?',(table_id,))
                    for p, qty in rows:
                        if p['inventory_managed']:
                            db.execute('UPDATE products SET stock=stock-? WHERE id=?',(qty,p['id']))
                    products_by_id = {p['id']:p for p, qty in rows}
                    for pid, qty, notes in order_lines:
                        p = products_by_id[pid]
                        db.execute('INSERT INTO items(sale_id,product_id,name,quantity,price,notes,inventory_managed_at_sale) VALUES(?,?,?,?,?,?,?)',(sid,pid,p['name'],qty,unit_price(p,notes),notes,p['inventory_managed']))
                    extra = {'receipt': {'id': sid, 'total':total, 'change':received-total}}
                else:
                    self.reply(404, {'error':'No encontrado'})
                    return
                db.commit()
                self.reply(200, {**self.state(db), **extra})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, OverflowError) as e:
            self.reply(400, {'error': str(e) if isinstance(e, ValueError) else 'Datos inválidos.'})
        except sqlite3.Error:
            self.reply(500, {'error':'No se pudo guardar la operación.'})

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    user = os.environ.get('JOSBAL_USER', '')
    password = os.environ.get('JOSBAL_PASSWORD', '')
    if (host != '127.0.0.1' or user or password) and (not user or ':' in user or len(password) < 16):
        raise SystemExit('Configura JOSBAL_USER (sin dos puntos) y JOSBAL_PASSWORD de al menos 16 caracteres antes de permitir acceso de red.')
    BACKUPS.start()
    server = ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),Handler)
    print('JOSBAL-POST listo en puerto',server.server_port,flush=True)
    server.serve_forever()
