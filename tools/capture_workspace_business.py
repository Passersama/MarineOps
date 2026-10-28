"""Hash ordered business rows, excluding separately checked additive coordination and management metadata."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

directory=Path(sys.argv[1]).resolve()
result={}
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    path=directory/name
    conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                if r[0] not in ('ledger_meta','import_keys','module_history','removed_berth_history')]
        data={table:list(conn.execute('SELECT * FROM "'+table.replace('"','""')+'" ORDER BY rowid')) for table in tables}
        result[name]={'sha256':hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                      'counts':{table:len(rows) for table,rows in data.items()}}
    finally:conn.close()
print(json.dumps(result,ensure_ascii=False))
