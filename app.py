import json
import base64
import hmac
import uuid
import os
import sqlite3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent
DB = Path(os.environ.get('JOSBAL_DB', ROOT / 'data' / 'josbal.sqlite3'))
DB.parent.mkdir(parents=True, exist_ok=True)

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

with connect() as db:
    db.executescript('''
    CREATE TABLE IF NOT EXISTS dining_tables(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS table_orders(table_id INTEGER PRIMARY KEY REFERENCES dining_tables(id), items TEXT NOT NULL, updated TEXT NOT NULL, revision TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>0), stock INTEGER NOT NULL CHECK(stock>=0));
    CREATE TABLE IF NOT EXISTS shifts(id INTEGER PRIMARY KEY, opened TEXT NOT NULL, opening INTEGER NOT NULL, closed TEXT, counted INTEGER);
    CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL REFERENCES shifts(id), created TEXT NOT NULL, total INTEGER NOT NULL, payment TEXT NOT NULL, received INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS items(sale_id INTEGER REFERENCES sales(id), product_id INTEGER REFERENCES products(id), name TEXT NOT NULL, quantity INTEGER NOT NULL, price INTEGER NOT NULL);
    ''')
    # Additive migration preserves existing products, inventory and sales.
    columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
    for name, definition in [('category', "TEXT NOT NULL DEFAULT ''"), ('description', "TEXT NOT NULL DEFAULT ''"), ('inventory_managed', 'INTEGER NOT NULL DEFAULT 1'), ('menu_key', 'TEXT')]:
        if name not in columns:
            db.execute(f'ALTER TABLE products ADD COLUMN {name} {definition}')
    if 'notes' not in {r['name'] for r in db.execute('PRAGMA table_info(items)')}:
        db.execute("ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    sales_columns = {r['name'] for r in db.execute('PRAGMA table_info(sales)')}
    if 'table_id' not in sales_columns:
        db.execute('ALTER TABLE sales ADD COLUMN table_id INTEGER REFERENCES dining_tables(id)')
    if 'table_name' not in sales_columns:
        db.execute("ALTER TABLE sales ADD COLUMN table_name TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS products_menu_key ON products(menu_key)')
    if os.environ.get('JOSBAL_IMPORT_MENU', '1') == '1':
        menu = json.loads((ROOT / 'catalog' / 'menu.json').read_text())
        for item in menu['items']:
            db.execute('INSERT OR IGNORE INTO products(name,price,stock,category,description,inventory_managed,menu_key) VALUES(?,?,0,?,?,0,?)', (item['name'],item['price'],item['category'],item['description'],item['key']))

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

def snapshot(db):
    shift = db.execute('SELECT * FROM shifts WHERE closed IS NULL ORDER BY id DESC LIMIT 1').fetchone()
    sales = [dict(r) for r in db.execute('SELECT * FROM sales ORDER BY id DESC LIMIT 30')]
    for sale in sales:
        sale['items'] = [dict(r) for r in db.execute('SELECT product_id,name,quantity,price,notes FROM items WHERE sale_id=? ORDER BY rowid', (sale['id'],))]
    result = dict(shift) if shift else None
    if result:
        result['cash_sales'] = db.execute("SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND payment='cash'", (shift['id'],)).fetchone()[0]
        result['total_sales'] = db.execute('SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=?', (shift['id'],)).fetchone()[0]
        result['expected'] = result['opening'] + result['cash_sales']
    tables = [dict(r) for r in db.execute('SELECT * FROM dining_tables ORDER BY id')]
    orders = [dict(r) for r in db.execute('SELECT * FROM table_orders ORDER BY table_id')]
    for order in orders:
        order['items'] = json.loads(order['items'])
    return {'tables': tables, 'orders': orders, 'products': [dict(r) for r in db.execute('SELECT * FROM products ORDER BY name')], 'shift': result, 'sales': sales}

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()

    def authorized(self):
        username = os.environ.get('JOSBAL_USER', '')
        password = os.environ.get('JOSBAL_PASSWORD', '')
        if not username and not password and os.environ.get('HOST', '127.0.0.1') == '127.0.0.1':
            return True
        try:
            method, encoded = self.headers.get('Authorization', '').split(' ', 1)
            supplied = base64.b64decode(encoded, validate=True).decode('utf-8')
            user, secret = supplied.split(':', 1)
            valid = method == 'Basic' and hmac.compare_digest(user.encode(), username.encode()) and hmac.compare_digest(secret.encode(), password.encode())
        except (ValueError, UnicodeError):
            valid = False
        if valid and username and password:
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="JOSBAL", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/menu':
            with connect() as db:
                rows = db.execute('SELECT name,price,category,description FROM products WHERE menu_key IS NOT NULL ORDER BY menu_key')
                self.reply(200, {'currency':'MXN', 'items':[dict(r) for r in rows]})
            return
        public = {'/menu': 'menu.html', '/menu/': 'menu.html', '/menu.js': 'menu.js', '/menu.css': 'menu.css', '/menu.pdf': 'menu.pdf'}
        if self.path in public:
            file = ROOT / 'static' / public[self.path]
            raw = file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.pdf':'application/pdf'}[file.suffix])
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if not self.authorized():
            return
        if self.path == '/api/state':
            with connect() as db:
                self.reply(200, snapshot(db))
            return
        files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
        if self.path not in files:
            self.reply(404, {'error': 'No encontrado'})
            return
        file = ROOT / 'static' / files[self.path]
        raw = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[file.suffix[1:]])
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if not self.authorized():
            return
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.reply(403, {'error': 'Solicitud no permitida.'})
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
                if self.path == '/api/tables':
                    name = body.get('name', '')
                    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                        raise ValueError('Escribe un nombre de mesa de hasta 60 caracteres.')
                    name = name.strip()
                    tid = integer(body['id']) if body.get('id') else None
                    active = 0 if str(body.get('active', '1')) == '0' else 1
                    if tid and not active and db.execute('SELECT 1 FROM table_orders WHERE table_id=?',(tid,)).fetchone():
                        raise ValueError('Cobra el pedido pendiente antes de desactivar la mesa.')
                    if db.execute('SELECT 1 FROM dining_tables WHERE name=? COLLATE NOCASE AND id!=?',(name,tid or 0)).fetchone():
                        raise ValueError('Ya existe una mesa con ese nombre.')
                    if tid:
                        if db.execute('UPDATE dining_tables SET name=?,active=? WHERE id=?',(name,active,tid)).rowcount != 1:
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
                    if body.get('id'):
                        if db.execute('UPDATE products SET name=?,price=?,stock=?,category=?,description=?,inventory_managed=? WHERE id=?', (name,price,stock,category,description,managed,integer(body['id']))).rowcount != 1:
                            raise ValueError('Producto no encontrado.')
                    else:
                        db.execute('INSERT INTO products(name,price,stock,category,description,inventory_managed) VALUES(?,?,?,?,?,?)',(name,price,stock,category,description,managed))
                elif self.path == '/api/open':
                    if shift:
                        raise ValueError('La caja ya está abierta.')
                    db.execute('INSERT INTO shifts(opened,opening) VALUES(?,?)',(now(),money(body['opening'])))
                elif self.path == '/api/close':
                    if not shift:
                        raise ValueError('La caja está cerrada.')
                    counted = money(body['counted'])
                    expected = shift['opening'] + db.execute("SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND payment='cash'",(shift['id'],)).fetchone()[0]
                    db.execute('UPDATE shifts SET closed=?,counted=? WHERE id=?',(now(),counted,shift['id']))
                    extra = {'closing': {'expected': expected, 'counted': counted, 'difference': counted-expected}}
                elif self.path in ('/api/sales', '/api/orders'):
                    if not shift:
                        raise ValueError('Abre la caja antes de cobrar.')
                    saving_order = self.path == '/api/orders'
                    table_id = integer(body['table_id']) if body.get('table_id') else None
                    table = db.execute('SELECT * FROM dining_tables WHERE id=? AND active=1',(table_id,)).fetchone() if table_id else None
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
                        total += p['price']*qty
                    if saving_order:
                        clean_items = [{'id':pid,'quantity':qty,'notes':notes} for pid,qty,notes in order_lines]
                        db.execute('INSERT INTO table_orders(table_id,items,updated,revision) VALUES(?,?,?,?) ON CONFLICT(table_id) DO UPDATE SET items=excluded.items,updated=excluded.updated,revision=excluded.revision',(table_id,json.dumps(clean_items,ensure_ascii=False),now(),uuid.uuid4().hex))
                        db.commit()
                        self.reply(200, snapshot(db))
                        return
                    received = money(body.get('received',0)) if payment == 'cash' else total
                    if received < total:
                        raise ValueError('El efectivo recibido es insuficiente.')
                    sid = db.execute('INSERT INTO sales(shift_id,created,total,payment,received) VALUES(?,?,?,?,?)',(shift['id'],now(),total,payment,received)).lastrowid
                    db.execute('UPDATE sales SET table_id=?,table_name=? WHERE id=?',(table_id,table['name'] if table else '',sid))
                    if pending:
                        db.execute('DELETE FROM table_orders WHERE table_id=?',(table_id,))
                    for p, qty in rows:
                        if p['inventory_managed']:
                            db.execute('UPDATE products SET stock=stock-? WHERE id=?',(qty,p['id']))
                    products_by_id = {p['id']:p for p, qty in rows}
                    for pid, qty, notes in order_lines:
                        p = products_by_id[pid]
                        db.execute('INSERT INTO items(sale_id,product_id,name,quantity,price,notes) VALUES(?,?,?,?,?,?)',(sid,pid,p['name'],qty,p['price'],notes))
                    extra = {'receipt': {'id': sid, 'total':total, 'change':received-total}}
                else:
                    self.reply(404, {'error':'No encontrado'})
                    return
                db.commit()
                self.reply(200, {**snapshot(db), **extra})
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
    server = ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),Handler)
    print('JOSBAL-POST listo en puerto',server.server_port,flush=True)
    server.serve_forever()
