from pathlib import Path
import sqlite3
import tempfile
import unittest
from backups import Backups,restore_to_copy

class BackupRecovery(unittest.TestCase):
    def test_live_backup_restore_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE sales(id INTEGER PRIMARY KEY,total INTEGER)')
                db.execute('INSERT INTO sales VALUES(1,14000)')
                db.execute('CREATE TABLE sessions(token_hash TEXT PRIMARY KEY)')
                db.execute("INSERT INTO sessions VALUES('old-session-hash')")
            manager=Backups(path,keep=2)
            first=manager.create()
            restored=Path(tmp)/'restored'
            restore_to_copy(first,restored)
            with sqlite3.connect(restored) as db:
                self.assertEqual(db.execute('SELECT total FROM sales').fetchone()[0],14000)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            with self.assertRaises(ValueError):restore_to_copy(first,path)
            with self.assertRaises(ValueError):manager.file('../db')
            manager.create();manager.create()
            self.assertEqual(len(manager.listing()),2)
            self.assertFalse(first.exists())
            with sqlite3.connect(path) as db:self.assertEqual(db.execute('SELECT total FROM sales').fetchone()[0],14000)
