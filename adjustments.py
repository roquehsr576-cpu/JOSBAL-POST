import json

REASONS = ('Cliente cambió de opinión','Error al tomar el pedido','Producto agotado','Demora en el servicio','Problema de calidad','Otro')

def reason_from(body):
    reason, notes = body.get('reason'), body.get('reason_notes', '')
    if reason not in REASONS:
        raise ValueError('Selecciona el motivo del cambio o cancelación.')
    if not isinstance(notes, str) or len(notes) > 300:
        raise ValueError('Los detalles del motivo deben tener hasta 300 caracteres.')
    if reason == 'Otro' and not notes.strip():
        raise ValueError('Describe el motivo cuando eliges “Otro”.')
    return reason, notes.strip()

def removed_lines(previous, current):
    # Lines are matched by product and preparation: a changed preparation counts as a removal.
    left = {}
    for line in current:
        key = (line['id'], line['notes'])
        left[key] = left.get(key, 0) + line['quantity']
    removed = []
    for line in previous:
        key = (line['id'], line.get('notes', ''))
        kept = min(left.get(key, 0), line['quantity'])
        left[key] = left.get(key, 0) - kept
        if line['quantity'] > kept:
            removed.append({'id': line['id'], 'quantity': line['quantity'] - kept, 'notes': line.get('notes', '')})
    return removed

def log_adjustment(db, kind, reason, notes, lines, timestamp, table_name, production_order_id=None, sale_id=None, amount=None):
    items = []
    for line in lines:
        p = db.execute('SELECT name,price FROM products WHERE id=?', (line['id'],)).fetchone()
        items.append({'id': line['id'], 'name': line.get('name') or (p['name'] if p else 'Producto'), 'quantity': line['quantity'], 'price': line.get('price', p['price'] if p else 0), 'notes': line.get('notes', '')})
    if amount is None:
        amount = sum(i['price'] * i['quantity'] for i in items)
    db.execute('INSERT INTO adjustments(created,kind,reason,notes,items,amount,table_name,sale_id,production_order_id) VALUES(?,?,?,?,?,?,?,?,?)', (timestamp, kind, reason, notes, json.dumps(items, ensure_ascii=False), amount, table_name, sale_id, production_order_id))

def adjustments(db, limit=200):
    rows = [dict(r) for r in db.execute('SELECT * FROM adjustments ORDER BY id DESC LIMIT ?', (limit,))]
    for row in rows:
        row['items'] = json.loads(row['items'])
    return rows
