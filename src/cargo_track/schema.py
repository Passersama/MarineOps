"""Versioned SQLite schema and defensive connection setup."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from uuid import uuid4

from .domain import normalized_name

SCHEMA_VERSION = 1

DDL = r"""
CREATE TABLE IF NOT EXISTS schema_meta (
  id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL
);
INSERT OR IGNORE INTO schema_meta VALUES(1, 1);

CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK(kind IN ('VESSEL','SHORE')),
  name TEXT NOT NULL,
  name_key TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_shore_location ON locations(kind) WHERE kind='SHORE';

CREATE TABLE IF NOT EXISTS cargo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cargo_tag TEXT UNIQUE,
  default_description TEXT NOT NULL,
  physical_id TEXT,
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transfer_legs (
  no INTEGER PRIMARY KEY AUTOINCREMENT,
  cargo_id INTEGER NOT NULL REFERENCES cargo(id) ON DELETE RESTRICT,
  predecessor_no INTEGER REFERENCES transfer_legs(no) ON DELETE RESTRICT,
  from_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  from_name_snapshot TEXT NOT NULL,
  to_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  to_name_snapshot TEXT NOT NULL,
  description TEXT NOT NULL CHECK(length(trim(description))>0),
  comment TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('Waiting','On Board','Done')),
  is_void INTEGER NOT NULL DEFAULT 0 CHECK(is_void IN (0,1)),
  version INTEGER NOT NULL DEFAULT 0,
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  completed_utc TEXT,
  completed_date TEXT,
  completed_tz TEXT,
  CHECK ((status='Done' AND completed_utc IS NOT NULL AND completed_date IS NOT NULL AND completed_tz IS NOT NULL)
     OR (status!='Done' AND completed_utc IS NULL AND completed_date IS NULL AND completed_tz IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_transfer_per_cargo
  ON transfer_legs(cargo_id) WHERE is_void=0 AND status IN ('Waiting','On Board');
CREATE INDEX IF NOT EXISTS transfer_cargo_order ON transfer_legs(cargo_id, no);
CREATE INDEX IF NOT EXISTS transfer_from_status ON transfer_legs(from_location_id, status, is_void, no);
CREATE INDEX IF NOT EXISTS transfer_to_status ON transfer_legs(to_location_id, status, is_void, no);

CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL CHECK(entity_type IN ('cargo','transfer','location','voyage','stop','settings')),
  entity_id INTEGER NOT NULL,
  command_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_utc TEXT NOT NULL,
  timezone_name TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  data_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_entity_order ON audit_events(entity_type,entity_id,id);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
  BEGIN SELECT RAISE(ABORT,'audit events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
  BEGIN SELECT RAISE(ABORT,'audit events are immutable'); END;

CREATE TABLE IF NOT EXISTS voyages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL CHECK(length(trim(name))>0),
  is_current INTEGER NOT NULL DEFAULT 0 CHECK(is_current IN (0,1)),
  archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  CHECK(NOT(is_current=1 AND archived=1))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_current_voyage ON voyages(is_current) WHERE is_current=1;

CREATE TABLE IF NOT EXISTS voyage_stops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  voyage_id INTEGER NOT NULL REFERENCES voyages(id) ON DELETE RESTRICT,
  vessel_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  vessel_name_snapshot TEXT NOT NULL,
  position INTEGER NOT NULL,
  removed INTEGER NOT NULL DEFAULT 0 CHECK(removed IN (0,1)),
  created_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS unique_active_voyage_stop_position
  ON voyage_stops(voyage_id,position) WHERE removed=0;
CREATE INDEX IF NOT EXISTS voyage_stops_route ON voyage_stops(voyage_id,removed,position);
CREATE TRIGGER IF NOT EXISTS stop_voyage_immutable BEFORE UPDATE OF voyage_id ON voyage_stops
  WHEN NEW.voyage_id != OLD.voyage_id
  BEGIN SELECT RAISE(ABORT,'a stop cannot move between voyages'); END;
CREATE TRIGGER IF NOT EXISTS archived_voyage_stop_insert BEFORE INSERT ON voyage_stops
  WHEN EXISTS(SELECT 1 FROM voyages WHERE id=NEW.voyage_id AND archived=1)
  BEGIN SELECT RAISE(ABORT,'a historical voyage is read-only'); END;
CREATE TRIGGER IF NOT EXISTS archived_voyage_stop_update BEFORE UPDATE ON voyage_stops
  WHEN EXISTS(SELECT 1 FROM voyages WHERE id=OLD.voyage_id AND archived=1)
  BEGIN SELECT RAISE(ABORT,'a historical voyage is read-only'); END;
CREATE TRIGGER IF NOT EXISTS archived_voyage_stop_delete BEFORE DELETE ON voyage_stops
  WHEN EXISTS(SELECT 1 FROM voyages WHERE id=OLD.voyage_id AND archived=1)
  BEGIN SELECT RAISE(ABORT,'a historical voyage is read-only'); END;

CREATE TABLE IF NOT EXISTS app_state (
  id INTEGER PRIMARY KEY CHECK(id=1),
  current_voyage_id INTEGER REFERENCES voyages(id) ON DELETE RESTRICT,
  current_stop_id INTEGER REFERENCES voyage_stops(id) ON DELETE RESTRICT,
  data_revision INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO app_state(id,current_voyage_id,current_stop_id,data_revision) VALUES(1,NULL,NULL,0);
CREATE TRIGGER IF NOT EXISTS current_stop_insert_valid BEFORE INSERT ON app_state
  WHEN NEW.current_stop_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM voyage_stops s WHERE s.id=NEW.current_stop_id
      AND s.voyage_id=NEW.current_voyage_id AND s.removed=0)
  BEGIN SELECT RAISE(ABORT,'current stop is not in the current voyage'); END;
CREATE TRIGGER IF NOT EXISTS current_stop_update_valid BEFORE UPDATE OF current_voyage_id,current_stop_id ON app_state
  WHEN NEW.current_stop_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM voyage_stops s WHERE s.id=NEW.current_stop_id
      AND s.voyage_id=NEW.current_voyage_id AND s.removed=0)
  BEGIN SELECT RAISE(ABORT,'current stop is not in the current voyage'); END;
CREATE TRIGGER IF NOT EXISTS current_stop_removal_valid BEFORE UPDATE OF removed ON voyage_stops
  WHEN NEW.removed=1 AND EXISTS (SELECT 1 FROM app_state WHERE current_stop_id=OLD.id)
  BEGIN SELECT RAISE(ABORT,'clear current stop before removing it'); END;

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS command_receipts (
  command_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  result_json TEXT NOT NULL,
  revision INTEGER NOT NULL,
  completed_utc TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        return conn
    except Exception:
        conn.close()
        raise


def initialize(conn: sqlite3.Connection) -> None:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone()
    if not exists and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
        raise RuntimeError('Choose a MarineOps ledger. This database belongs to another module.')
    if exists:
        version_row = conn.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()
        if version_row and version_row[0] > SCHEMA_VERSION:
            raise RuntimeError(f"Database schema {version_row[0]} is newer than this application ({SCHEMA_VERSION}).")
    conn.executescript(DDL)
    conn.execute("CREATE TABLE IF NOT EXISTS ledger_meta(id INTEGER PRIMARY KEY CHECK(id=1),identity TEXT NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO ledger_meta VALUES(1,?)",(str(uuid4()),))
    version = conn.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Database schema {version} is newer than this application ({SCHEMA_VERSION}).")
    if version < SCHEMA_VERSION:
        raise RuntimeError(f"No migration is available from database schema {version}.")
    now = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"
    conn.execute(
        f"INSERT INTO locations(kind,name,name_key,active,created_utc,updated_utc) "
        f"SELECT 'SHORE','xx port','xx port',1,{now},{now} "
        f"WHERE NOT EXISTS(SELECT 1 FROM locations WHERE kind='SHORE')"
    )
    conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_utc) VALUES('business_timezone','Asia/Riyadh',strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_utc) VALUES('transfer_vessel_name','',strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    # Port is the existing SHORE identity; older legs and saved plans keep their snapshots.
    shore = conn.execute("SELECT id,name FROM locations WHERE kind='SHORE'").fetchone()
    conn.execute("BEGIN IMMEDIATE")
    try:
        default_port = "xx port" if normalized_name(shore["name"]) == "on shore" else shore["name"]
        conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_utc) VALUES('port_name',?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))", (default_port,))
        port = conn.execute("SELECT value FROM settings WHERE key='port_name'").fetchone()[0]
        if shore["name"] != port:
            conn.execute("UPDATE locations SET name=?,name_key=?,updated_utc=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (port, normalized_name(port), shore["id"]))
            conn.execute("UPDATE app_state SET data_revision=data_revision+1 WHERE id=1")
            conn.execute("""INSERT INTO audit_events(entity_type,entity_id,command_id,event_type,occurred_utc,timezone_name,reason,data_json)
              VALUES('location',?,'shared-port-migration','PORT_NAME_MIGRATED',strftime('%Y-%m-%dT%H:%M:%SZ','now'),
              (SELECT value FROM settings WHERE key='business_timezone'),'Unify legacy shore with the configured port',?)""",
              (shore["id"], json.dumps({"before":{"name":shore["name"]},"after":{"name":port}},ensure_ascii=False)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def check_integrity(path: str) -> list[str]:
    conn = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
    conn.row_factory = sqlite3.Row
    try:
        failures = [str(row[0]) for row in conn.execute("PRAGMA integrity_check") if row[0] != "ok"]
        failures.extend(f"foreign key: {tuple(row)}" for row in conn.execute("PRAGMA foreign_key_check"))
        reference=sqlite3.connect(':memory:')
        try:
            reference.executescript(DDL)
            allowed_executable = set(reference.execute(
                "SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view')"))
            for schema_object in conn.execute(
                    "SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view')"):
                if tuple(schema_object) not in allowed_executable:
                    failures.append('Cargo backup contains an unsupported trigger or view')
            for kind,name,sql in reference.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"):
                actual=conn.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',(kind,name)).fetchone()
                normalize=lambda value:''.join(value.casefold().split()).replace('ifnotexists','')
                if actual is None or (sql and normalize(actual[0] or '')!=normalize(sql)):
                    failures.append(f'Missing or invalid Cargo schema object: {name}')
                elif kind=='table' and [tuple(r) for r in conn.execute(f'PRAGMA table_info("{name}")')] != list(reference.execute(f'PRAGMA table_info("{name}")')):
                    failures.append(f'Invalid Cargo table columns: {name}')
        finally:reference.close()
        if failures:return failures
        version = conn.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()
        if version is None or version[0] != SCHEMA_VERSION:
            failures.append("Unsupported schema version")
        bad_current = conn.execute("""SELECT a.id FROM app_state a WHERE a.current_stop_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM voyage_stops s WHERE s.id=a.current_stop_id AND s.voyage_id=a.current_voyage_id AND s.removed=0)""").fetchall()
        if bad_current:
            failures.append("Current stop does not belong to the current voyage")
        bad_dates = conn.execute("""SELECT no FROM transfer_legs WHERE
          (status='Done' AND (completed_utc IS NULL OR completed_date IS NULL OR completed_tz IS NULL)) OR
          (status!='Done' AND (completed_utc IS NOT NULL OR completed_date IS NOT NULL OR completed_tz IS NOT NULL))""").fetchall()
        if bad_dates:
            failures.append("Completed date fields do not match the transfer status")
        return failures
    finally:
        conn.close()
