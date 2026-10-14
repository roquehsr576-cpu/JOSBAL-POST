from pathlib import Path
import sqlite3
import threading
import time
from datetime import datetime,timezone

class Backups:
    def __init__(self,dbpath,directory=None,keep=14):
        self.dbpath=Path(dbpath)
        self.directory=Path(directory) if directory else self.dbpath.parent/'backups'
        self.keep=keep
        self.lock=threading.Lock()
        self.error=None

    def create(self,label='manual'):
        with self.lock:
            self.directory.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            target=self.directory/f'josbal-{stamp}-{label}.sqlite3'
            temporary=target.with_suffix('.tmp')
            try:
                with sqlite3.connect(self.dbpath) as source,sqlite3.connect(temporary) as destination:
                    source.backup(destination)
                    if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('El respaldo no pasó la comprobación de integridad.')
                temporary.chmod(0o600)
                temporary.replace(target)
                self.error=None
                files=sorted(self.directory.glob('josbal-*.sqlite3'),reverse=True)
                for old in files[self.keep:]:old.unlink()
                return target
            except Exception as error:
                temporary.unlink(missing_ok=True)
                self.error='No se pudo completar el respaldo. Revisa espacio y permisos del disco.'
                raise

    def listing(self):
        if not self.directory.exists():return []
        return [{'name':p.name,'size':p.stat().st_size,'created':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in sorted(self.directory.glob('josbal-*.sqlite3'),reverse=True)]

    def file(self,name):
        if name not in {b['name'] for b in self.listing()}:raise ValueError('Respaldo no encontrado.')
        return self.directory/name

    def start(self,interval=21600):
        def loop():
            while True:
                try:self.create('auto')
                except Exception:pass
                time.sleep(interval)
        threading.Thread(target=loop,daemon=True).start()


def restore_to_copy(backup,destination):
    # Never overwrite an existing database, especially the live production database.
    destination=Path(destination)
    if destination.exists():raise ValueError('El destino ya existe. Usa una ruta nueva.')
    source=sqlite3.connect(f'file:{Path(backup).resolve()}?mode=ro',uri=True)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Respaldo inválido.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(destination) as restored:
            source.backup(restored)
            if restored.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone():restored.execute('DELETE FROM sessions')
            if restored.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restauración inválida.')
        destination.chmod(0o600)
    finally:source.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Restaurar un respaldo de JOSBAL en una copia nueva.')
    parser.add_argument('backup');parser.add_argument('destination');args=parser.parse_args()
    restore_to_copy(args.backup,args.destination)
    print('Copia restaurada y verificada. La base en uso no se modificó.')
