"""Hash every stored business row, independently of optional index migrations."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def snapshot(directory):
    result = {}
    for name in ('cargo-track.sqlite3', 'personnel-transfer.sqlite3'):
        path = (Path(directory)/name).resolve()
        connection = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
        try:
            connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            content = {table:list(connection.execute('SELECT * FROM "'+table.replace('"','""')+'" ORDER BY rowid')) for table in tables}
            encoded = json.dumps(content,sort_keys=True,ensure_ascii=False,default=lambda value:value.hex()).encode('utf-8')
            result[name] = {'sha256':hashlib.sha256(encoded).hexdigest(),
                            'table_rows':{table:len(rows) for table,rows in content.items()}}
        finally:
            connection.close()
    return result


if __name__=='__main__':
    print(json.dumps(snapshot(sys.argv[1]),sort_keys=True))
