import json
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
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>0), stock INTEGER NOT NULL CHECK(stock>=0));
    CREATE TABLE IF NOT EXISTS shifts(id INTEGER PRIMARY KEY, opened TEXT NOT NULL, opening INTEGER NOT NULL, closed TEXT, counted INTEGER);
    CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL REFERENCES shifts(id), created TEXT NOT NULL, total INTEGER NOT NULL, payment TEXT NOT NULL, received INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS items(sale_id INTEGER REFERENCES sales(id), product_id INTEGER REFERENCES products(id), name TEXT NOT NULL, quantity INTEGER NOT NULL, price INTEGER NOT NULL);
    ''')

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
    result = dict(shift) if shift else None
    if result:
        result['cash_sales'] = db.execute("SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=? AND payment='cash'", (shift['id'],)).fetchone()[0]
        result['total_sales'] = db.execute('SELECT coalesce(sum(total),0) FROM sales WHERE shift_id=?', (shift['id'],)).fetchone()[0]
        result['expected'] = result['opening'] + result['cash_sales']
    return {'products': [dict(r) for r in db.execute('SELECT * FROM products ORDER BY name')], 'shift': result, 'sales': sales}

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
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
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 65536:
                raise ValueError('Solicitud demasiado grande.')
            body = json.loads(self.rfile.read(length))
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                shift = db.execute('SELECT * FROM shifts WHERE closed IS NULL').fetchone()
                extra = {}
                if self.path == '/api/products':
                    name = str(body['name']).strip()
                    price, stock = money(body['price']), integer(body['stock'])
                    if not name or len(name) > 120 or price <= 0:
                        raise ValueError('Introduce un nombre y un precio mayor que cero.')
                    if body.get('id'):
                        if db.execute('UPDATE products SET name=?,price=?,stock=? WHERE id=?', (name,price,stock,integer(body['id']))).rowcount != 1:
                            raise ValueError('Producto no encontrado.')
                    else:
                        db.execute('INSERT INTO products(name,price,stock) VALUES(?,?,?)',(name,price,stock))
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
                elif self.path == '/api/sales':
                    if not shift:
                        raise ValueError('Abre la caja antes de cobrar.')
                    payment = body['payment']
                    if payment not in ('cash','card'):
                        raise ValueError('Método de pago inválido.')
                    quantities = {}
                    for item in body['items']:
                        pid, qty = integer(item['id']), integer(item['quantity'])
                        if qty == 0:
                            raise ValueError('La cantidad debe ser mayor que cero.')
                        quantities[pid] = quantities.get(pid, 0) + qty
                    if not quantities:
                        raise ValueError('Agrega productos a la venta.')
                    rows, total = [], 0
                    for pid, qty in quantities.items():
                        p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                        if not p or p['stock'] < qty:
                            raise ValueError('Stock insuficiente. Actualiza la venta.')
                        rows.append((p,qty))
                        total += p['price']*qty
                    received = money(body.get('received',0)) if payment == 'cash' else total
                    if received < total:
                        raise ValueError('El efectivo recibido es insuficiente.')
                    sid = db.execute('INSERT INTO sales(shift_id,created,total,payment,received) VALUES(?,?,?,?,?)',(shift['id'],now(),total,payment,received)).lastrowid
                    for p, qty in rows:
                        db.execute('UPDATE products SET stock=stock-? WHERE id=?',(qty,p['id']))
                        db.execute('INSERT INTO items VALUES(?,?,?,?,?)',(sid,p['id'],p['name'],qty,p['price']))
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
    server = ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),Handler)
    print('JOSBAL-POST listo en puerto',server.server_port,flush=True)
    server.serve_forever()
