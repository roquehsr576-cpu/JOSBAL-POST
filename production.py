import json
import uuid

BAR_CATEGORIES = frozenset(('Bebidas calientes','Tizanas calientes','Tés','Refrescantes','Chamoyadas','Bebidas sobre las rocas','Sodas italianas','Frappés','Malteadas','Smoothies','Waffles','Pasteles','Postres','Croissants dulces','Croissants salados','Croissant','Croissants','Crepas dulces','Crepas'))

def station_for(product):
    station = product['production_station']
    return station if station in ('kitchen','bar') else ('bar' if product['category'] in BAR_CATEGORIES else 'kitchen')

def tickets(db, order_id=None):
    where = 'WHERE t.order_id=?' if order_id else "WHERE t.status!='ready' OR t.id IN (SELECT id FROM production_tickets WHERE status='ready' ORDER BY id DESC LIMIT 50)"
    rows = db.execute(f'SELECT t.*,o.table_name,o.created,o.sale_id FROM production_tickets t JOIN production_orders o ON o.id=t.order_id {where} ORDER BY o.id,t.id', (order_id,) if order_id else ())
    result=[]
    for r in rows:
        ticket=dict(r)
        ticket['items']=json.loads(ticket['items'])
        ticket['changes']=json.loads(ticket['changes'])
        result.append(ticket)
    return result

def send_tickets(db, lines, table_name, timestamp, order_id=None, sale_id=None):
    if not order_id:
        order_id=db.execute('INSERT INTO production_orders(table_name,created,sale_id) VALUES(?,?,?)',(table_name,timestamp,sale_id)).lastrowid
    else:
        db.execute('UPDATE production_orders SET table_name=?,sale_id=coalesce(?,sale_id) WHERE id=?',(table_name,sale_id,order_id))
    grouped={'kitchen':[],'bar':[]}
    for pid,qty,notes in lines:
        p=db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
        grouped[station_for(p)].append({'id':pid,'name':p['name'],'quantity':qty,'notes':notes,'prep_minutes':p['prep_minutes']})
    for station,items in grouped.items():
        existing=db.execute('SELECT * FROM production_tickets WHERE order_id=? AND station=?',(order_id,station)).fetchone()
        # An untouched saved order is not resent when it is paid.
        if existing:
            previous=json.loads(existing['items'])
            # Product time edits must not resend an unchanged kitchen/bar ticket at payment.
            comparable=lambda lines:[{k:v for k,v in line.items() if k!='prep_minutes'} for line in lines]
            if comparable(previous)==comparable(items):
                continue
        if not items and not existing:
            continue
        # Keep the previous and current complete lists to make removals explicit.
        changes={'previous':json.loads(existing['items']),'current':items} if existing else {}
        status='pending'
        revision=uuid.uuid4().hex
        db.execute('INSERT INTO production_tickets(order_id,station,items,changes,status,updated,revision) VALUES(?,?,?,?,?,?,?) ON CONFLICT(order_id,station) DO UPDATE SET items=excluded.items,changes=excluded.changes,status=excluded.status,updated=excluded.updated,revision=excluded.revision',(order_id,station,json.dumps(items,ensure_ascii=False),json.dumps(changes,ensure_ascii=False),status,timestamp,revision))
    return order_id

def cancel_tickets(db, order_id, timestamp):
    # Ready tickets were already delivered; only tickets still in preparation are withdrawn.
    for t in db.execute("SELECT * FROM production_tickets WHERE order_id=? AND status!='ready'",(order_id,)).fetchall():
        items=json.loads(t['items'])
        if not items:
            continue
        db.execute('UPDATE production_tickets SET items=?,changes=?,status=?,updated=?,revision=? WHERE id=?',('[]',json.dumps({'previous':items,'current':[]},ensure_ascii=False),'pending',timestamp,uuid.uuid4().hex,t['id']))
