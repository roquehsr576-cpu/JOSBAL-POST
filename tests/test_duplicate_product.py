import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class DuplicateProduct(unittest.TestCase):
    def test_retires_only_identified_duplicate_and_preserves_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'db.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,price INTEGER NOT NULL,stock INTEGER NOT NULL,inventory_managed INTEGER NOT NULL DEFAULT 1,menu_key TEXT)')
                db.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)', [
                    (1, 'Hamburguesa clásica', 8000, 100, 1, None),
                    (2, 'Hamburguesa clásica', 8000, 0, 0, 'pdf-v1-024'),
                    (3, 'Otro producto', 8000, 100, 1, None),
                ])
            env = {**os.environ, 'JOSBAL_DB': str(path)}
            for _ in range(2):
                subprocess.run([sys.executable, '-c', 'import app'], env=env, check=True, capture_output=True)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT id,stock,retired FROM products WHERE id<=3 ORDER BY id').fetchall(), [(1,100,1),(2,0,0),(3,100,0)])
