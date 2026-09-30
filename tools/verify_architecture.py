"""Executable evidence for selected R2 constraints, not a production repository.

Uses an isolated in-memory SQLite database and a small reference command.
It does not claim to exercise PySide6, packaging, migrations or disk restore.
"""
from pathlib import Path
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DDL = '''
PRAGMA foreign_keys=ON;
CREATE TABLE cargo(id INTEGER PRIMARY KEY);
CREATE TABLE legs(
 no INTEGER PRIMARY KEY AUTOINCREMENT,
 cargo_id INTEGER NOT NULL REFERENCES cargo(id),
 predecessor INTEGER REFERENCES legs(no),
 status TEXT NOT NULL CHECK(status IN ('Waiting','On Board','Done')),
 is_void INTEGER NOT NULL DEFAULT 0 CHECK(is_void IN (0,1)),
 version INTEGER NOT NULL DEFAULT 0,
 completed_utc TEXT, completed_date TEXT, completed_tz TEXT,
 CHECK((status='Done' AND completed_utc IS NOT NULL AND completed_date IS NOT NULL AND completed_tz IS NOT NULL)
    OR (status!='Done' AND completed_utc IS NULL AND completed_date IS NULL AND completed_tz IS NULL))
);
CREATE UNIQUE INDEX one_open ON legs(cargo_id) WHERE is_void=0 AND status IN ('Waiting','On Board');
CREATE TABLE events(id INTEGER PRIMARY KEY, leg_id INTEGER NOT NULL REFERENCES legs(no), note TEXT NOT NULL);
CREATE TABLE receipts(command_id TEXT PRIMARY KEY, leg_id INTEGER NOT NULL REFERENCES legs(no));
CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
INSERT INTO meta VALUES(1,0);
CREATE TABLE voyages(id INTEGER PRIMARY KEY);
CREATE TABLE stops(id INTEGER PRIMARY KEY, voyage_id INTEGER NOT NULL REFERENCES voyages(id), vessel TEXT NOT NULL, position INTEGER NOT NULL, removed INTEGER NOT NULL DEFAULT 0 CHECK(removed IN (0,1)));
CREATE UNIQUE INDEX unique_position ON stops(voyage_id,position) WHERE removed=0;
CREATE TABLE app_state(id INTEGER PRIMARY KEY CHECK(id=1), voyage_id INTEGER REFERENCES voyages(id), stop_id INTEGER REFERENCES stops(id));
CREATE TRIGGER current_stop_insert BEFORE INSERT ON app_state
WHEN NEW.stop_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM stops WHERE id=NEW.stop_id AND voyage_id=NEW.voyage_id AND removed=0)
BEGIN SELECT RAISE(ABORT,'current stop is not in voyage'); END;
CREATE TRIGGER current_stop_update BEFORE UPDATE ON app_state
WHEN NEW.stop_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM stops WHERE id=NEW.stop_id AND voyage_id=NEW.voyage_id AND removed=0)
BEGIN SELECT RAISE(ABORT,'current stop is not in voyage'); END;
CREATE TRIGGER immutable_stop_voyage BEFORE UPDATE OF voyage_id ON stops WHEN NEW.voyage_id!=OLD.voyage_id
BEGIN SELECT RAISE(ABORT,'stop cannot migrate'); END;
CREATE TRIGGER no_remove_current_stop BEFORE UPDATE OF removed ON stops WHEN NEW.removed=1 AND EXISTS(SELECT 1 FROM app_state WHERE stop_id=OLD.id)
BEGIN SELECT RAISE(ABORT,'clear current stop first'); END;
'''


def main():
    db = sqlite3.connect(':memory:')
    db.executescript(DDL)
    db.executemany('INSERT INTO cargo VALUES(?)',[(1,),(2,)])
    db.execute("INSERT INTO legs(cargo_id,status) VALUES(1,'Waiting')")
    db.executemany('INSERT INTO voyages VALUES(?)',[(1,),(2,),(3,)])
    db.executemany('INSERT INTO stops VALUES(?,?,?,?,0)',[(1,1,'BVC',1),(2,1,'CHA',2),(3,1,'BVC',3),(4,2,'DF2',1)])
    db.execute('INSERT INTO app_state VALUES(1,1,3)')
    db.commit()
    passed=[]

    def rejects(name,statement,args=()):
        try:
            with db:
                db.execute(statement,args)
        except sqlite3.IntegrityError:
            passed.append(name)
        else:
            raise AssertionError(f'Expected rejection: {name}')

    rejects('duplicate active transfer rejected',"INSERT INTO legs(cargo_id,status) VALUES(1,'On Board')")
    rejects('invalid completed-date combination rejected',"INSERT INTO legs(cargo_id,status) VALUES(2,'Done')")
    rejects('invalid cargo reference rejected',"INSERT INTO legs(cargo_id,status) VALUES(99,'Waiting')")
    rejects('cross-voyage current stop rejected','UPDATE app_state SET stop_id=4 WHERE id=1')
    rejects('current stop removal without clearing rejected','UPDATE stops SET removed=1 WHERE id=3')

    with db:
        db.execute("UPDATE legs SET status='Done',completed_utc='2026-09-29T22:30:00Z',completed_date='20260930',completed_tz='Asia/Riyadh' WHERE no=1")
        db.execute("INSERT INTO legs(cargo_id,predecessor,status) VALUES(1,1,'Waiting')")
    assert db.execute('SELECT count(*) FROM legs').fetchone()[0]==2
    passed.append('next transfer allowed after completion')

    with db:
        for stop_id in (1,2,3):
            db.execute('UPDATE stops SET position=? WHERE id=?',(-stop_id,stop_id))
        for position,stop_id in enumerate((3,2,1),1):
            db.execute('UPDATE stops SET position=? WHERE id=?',(position,stop_id))
    assert db.execute('SELECT stop_id FROM app_state').fetchone()[0]==3
    assert db.execute('SELECT vessel FROM stops WHERE voyage_id=1 ORDER BY position').fetchall()==[('BVC',),('CHA',),('BVC',)]
    passed.append('duplicate vessel reorder retains selected stop ID')
    with db:
        db.execute('UPDATE app_state SET stop_id=NULL WHERE id=1')
        db.execute('UPDATE stops SET removed=1 WHERE id=3')
    assert db.execute('SELECT stop_id FROM app_state').fetchone()[0] is None
    assert db.execute('SELECT count(*) FROM stops WHERE voyage_id=3').fetchone()[0]==0
    passed.append('current stop removal and empty voyage supported')

    before=db.execute('SELECT * FROM legs WHERE no=2').fetchone()
    try:
        with db:
            db.execute("UPDATE legs SET status='On Board',version=version+1 WHERE no=2")
            db.execute('UPDATE meta SET revision=revision+1')
            db.execute('INSERT INTO events(leg_id,note) VALUES(2,NULL)')
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError('Fault injection did not fail')
    assert db.execute('SELECT * FROM legs WHERE no=2').fetchone()==before
    assert db.execute('SELECT revision FROM meta').fetchone()[0]==0
    passed.append('event-write failure rolls back state version and revision')

    def pickup(command_id,expected_version):
        with db:
            existing=db.execute('SELECT leg_id FROM receipts WHERE command_id=?',(command_id,)).fetchone()
            if existing:
                return 'already committed'
            affected=db.execute("UPDATE legs SET status='On Board',version=version+1 WHERE no=2 AND version=? AND status='Waiting'",(expected_version,)).rowcount
            if affected!=1:
                raise ValueError('STALE_RECORD')
            db.execute("INSERT INTO events(leg_id,note) VALUES(2,'pickup')")
            db.execute('INSERT INTO receipts VALUES(?,2)',(command_id,))
            db.execute('UPDATE meta SET revision=revision+1')
        return 'committed'

    assert pickup('pickup-001',0)=='committed'
    assert pickup('pickup-001',0)=='already committed'
    assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1
    assert db.execute('SELECT revision FROM meta').fetchone()[0]==1
    passed.append('reference command retries do not duplicate committed event')
    try:
        pickup('pickup-002',0)
    except ValueError as error:
        assert str(error)=='STALE_RECORD'
        passed.append('stale reference command rejected')
    else:
        raise AssertionError('Stale version accepted')

    # A stored business date is a snapshot, not a display conversion.
    instant=datetime.fromisoformat('2026-09-29T22:30:00+00:00')
    assert instant.astimezone(ZoneInfo('Asia/Riyadh')).strftime('%Y%m%d')=='20260930'
    assert instant.astimezone(ZoneInfo('UTC')).strftime('%Y%m%d')=='20260929'
    assert db.execute('SELECT completed_date FROM legs WHERE no=1').fetchone()[0]=='20260930'
    passed.append('midnight time-zone conversion and date snapshot verified')

    copy=sqlite3.connect(':memory:')
    copy.execute('PRAGMA foreign_keys=ON')
    db.backup(copy)
    assert copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert copy.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert copy.execute('SELECT * FROM legs').fetchall()==db.execute('SELECT * FROM legs').fetchall()
    passed.append('SQLite Backup API snapshot matches committed source')
    assert db.execute('PRAGMA foreign_keys').fetchone()[0]==1
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    report=dict(date='2026-09-30',passed_count=len(passed),passed=passed,
                scope='In-memory SQLite constraints and reference commands only.',
                not_tested=['production application','full domain chain validation','UI threads or accessibility','disk restore failure recovery','packaging and migrations'])
    (ROOT/'tools'/'architecture_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    copy.close()
    db.close()


if __name__=='__main__':
    main()
