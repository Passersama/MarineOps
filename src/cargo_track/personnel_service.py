"""Independent personnel storage, imports, state transitions and plan versions."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .personnel_import import PersonnelError, digest, iso_date, key, text
from .text_case import personnel_record, legacy_personnel
from .personnel_cargo import location_signature
from .coordination import workspace_files, ProtectedFileError
from .personnel_routes import transfer_name, transfer_origin, person_identity, leg_order
from .plan_store import version_summaries, version_payload, latest_family_payloads, latest_family_payload, validate_plan_shape


DDL = """
CREATE TABLE IF NOT EXISTS module_meta(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,identity TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS module_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS personnel_plans(id TEXT PRIMARY KEY,name TEXT NOT NULL,date TEXT NOT NULL,created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_batches(id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES personnel_plans(id),
 file_name TEXT NOT NULL,file_hash TEXT NOT NULL,content_hash TEXT NOT NULL,sheet TEXT NOT NULL,mode TEXT NOT NULL,created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS passengers(id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES personnel_plans(id),
 payload TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('Waiting','On Board','Done','Cancelled')),
 version INTEGER NOT NULL DEFAULT 0,pickup_utc TEXT,drop_utc TEXT,completed_date TEXT,created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS personnel_history(id INTEGER PRIMARY KEY,task_id TEXT NOT NULL REFERENCES passengers(id),
 event TEXT NOT NULL,occurred_utc TEXT NOT NULL,reason TEXT NOT NULL,data TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON personnel_history BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON personnel_history BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
CREATE TABLE IF NOT EXISTS vessel_aliases(source_path TEXT NOT NULL,alias TEXT NOT NULL,vessel_id INTEGER NOT NULL,
 signature TEXT NOT NULL,PRIMARY KEY(source_path,alias));
CREATE TABLE IF NOT EXISTS berth_versions(id TEXT PRIMARY KEY,family_id TEXT NOT NULL,version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('Draft','Published')),payload TEXT NOT NULL,created_utc TEXT NOT NULL,
 UNIQUE(family_id,version));
CREATE TRIGGER IF NOT EXISTS berth_no_update BEFORE UPDATE ON berth_versions BEGIN SELECT RAISE(ABORT,'save a new version'); END;
CREATE TRIGGER IF NOT EXISTS berth_no_delete BEFORE DELETE ON berth_versions BEGIN SELECT RAISE(ABORT,'versions are immutable'); END;
"""
FIELDS = {"name", "position", "nationality", "date", "source_date", "direction", "vessel", "comment",
          "from_name", "to_name", "from_id", "to_id", "source_path", "from_signature", "to_signature",
          "source_row", "source_sheet", "source_cells", "original_values", "issues", "batch_id",
          "person_id", "leg_index", "previous_task_id", "text_case", "preserve_text_case"}
IMPORT_FIELDS = {"name", "position", "nationality", "vessel", "from_name", "to_name", "date", "comment", "task_id"}
IMPORT_DDL = """CREATE TABLE IF NOT EXISTS import_keys(signature TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL REFERENCES import_batches(id));"""
MANAGEMENT_DDL = """
CREATE TABLE IF NOT EXISTS removed_berth_history(version_id TEXT PRIMARY KEY REFERENCES berth_versions(id),removed_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS module_history(id INTEGER PRIMARY KEY,event TEXT NOT NULL,occurred_utc TEXT NOT NULL,data TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS module_history_no_update BEFORE UPDATE ON module_history BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS module_history_no_delete BEFORE DELETE ON module_history BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
"""
INDEX_DDL = """
CREATE INDEX IF NOT EXISTS passengers_plan ON passengers(plan_id);
CREATE INDEX IF NOT EXISTS personnel_history_task ON personnel_history(task_id,id);
CREATE INDEX IF NOT EXISTS berth_created ON berth_versions(created_utc DESC,version DESC);
"""
CHANGE_TRACKING_DDL = """
CREATE TEMP TABLE IF NOT EXISTS changed_crew_plans(plan_id TEXT PRIMARY KEY);
CREATE TEMP TRIGGER IF NOT EXISTS crew_inserted AFTER INSERT ON main.passengers BEGIN
 INSERT OR IGNORE INTO changed_crew_plans VALUES(NEW.plan_id); END;
CREATE TEMP TRIGGER IF NOT EXISTS crew_updated AFTER UPDATE ON main.passengers BEGIN
 INSERT OR IGNORE INTO changed_crew_plans VALUES(NEW.plan_id);
 INSERT OR IGNORE INTO changed_crew_plans VALUES(OLD.plan_id); END;
CREATE TEMP TRIGGER IF NOT EXISTS crew_deleted AFTER DELETE ON main.passengers BEGIN
 INSERT OR IGNORE INTO changed_crew_plans VALUES(OLD.plan_id); END;
"""


def now():
    return datetime.now(UTC).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def clean_payload(record):
    data = {f: record[f] for f in FIELDS if f in record}
    # Nested source maps must also obey the import whitelist.
    for f in ("original_values", "source_cells"):
        data[f] = {k: v for k, v in data.get(f, {}).items() if k in IMPORT_FIELDS}
    if 'text_case' in data:
        data['text_case'] = {field: {k: v for k, v in info.items()
            if ((k in {'raw','value'} and isinstance(v,str)) or
                (k=='preserve' and type(v) is bool) or (k=='version' and type(v) is int) or
                (k=='review' and isinstance(v,list) and all(isinstance(note,str) for note in v)))}
            for field, info in data['text_case'].items() if field in {'name', 'position'} and isinstance(info, dict)}
    if 'preserve_text_case' in data and type(data['preserve_text_case']) is not bool:
        data.pop('preserve_text_case')
    return data


def crew_vessel_name(record, side):
    """Use the vessel-side endpoint, including source values of older imports."""
    original = record.get('original_values', {})
    return (text(record.get(side + '_name')) or text(record.get('vessel'))
            or text(original.get(side + '_name')) or text(original.get('vessel')))


class PersonnelService:
    @classmethod
    def read_view(cls, connection, path):
        """Use normalization against an existing query-only read transaction."""
        view = cls.__new__(cls)
        view.db, view.path = connection, Path(path).resolve()
        return view

    def __init__(self, path):
        self.path = Path(path).resolve()
        workspace_files.register_database(self.path)
        self.maintenance = False
        self.recovery_files = {}
        self.recovery_marker=self.path.with_name(self.path.name+'.recovery-required.json')
        if self.recovery_marker.exists():
            try:recovery=json.loads(self.recovery_marker.read_text(encoding='utf-8'))
            except (OSError,ValueError):recovery={}
            raise PersonnelError(f"Personnel recovery is required. Preserve and recover the safety copy {recovery.get('safety_copy','listed in the recovery file')}. "
                                 f"After recovery, remove {self.recovery_marker} to reopen. No database changes were made.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        try:
            exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='module_meta'").fetchone()
            if exists and self.db.execute("SELECT version FROM module_meta WHERE id=1").fetchone()[0] != 1:
                raise PersonnelError("Unsupported personnel database version.")
            if exists:
                self.validate_file(self.path)
            elif self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise PersonnelError('This file belongs to another application. Choose a personnel database.')
            self.db.executescript(DDL)
            self.db.executescript(IMPORT_DDL)
            self.db.executescript('BEGIN IMMEDIATE;'+MANAGEMENT_DDL+'COMMIT;')
            self.db.execute("INSERT OR IGNORE INTO module_meta VALUES(1,1,?)", (str(uuid4()),))
            self.db.execute("INSERT OR IGNORE INTO module_settings VALUES('port_name','xxPort')")
            self.db.executescript(INDEX_DDL + CHANGE_TRACKING_DDL)
            if not exists:self.validate_file(self.path)
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def atomic(self):
        if self.maintenance:
            raise PersonnelError("Personnel data needs recovery. Close the app and recover from the preserved safety copy.")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute('DELETE FROM changed_crew_plans')
            yield
            changed = {r[0] for r in self.db.execute('SELECT plan_id FROM changed_crew_plans')}
            if changed:
                self._validate_live_chains(self.db, changed)
                self._sync_crew_plans(changed)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _sync_crew_plans(self, plan_ids):
        """Save one new current version per family in the same crew transaction."""
        from .crew_plan_sync import refresh_crew_plan
        from .personnel_cargo import read_cargo, crew_source_matches
        # Refresh older families first so automatic Dashboard selection keeps
        # following the most recently saved family after a shared roster edit.
        for plan in reversed(latest_family_payloads(self.db, plan_ids)):
            if plan.get('mode') != 'Final' or plan.get('personnel_plan_id') not in plan_ids:
                continue
            try:
                source = self.planning_source(read_cargo(plan['source_path'],
                    selected_cargo=plan.get('source_dependencies', {}).get('cargo_ids', [])))
                if not crew_source_matches(plan, source):
                    continue
                updated = refresh_crew_plan(plan, source, self.crew_records(plan['personnel_plan_id'], source),
                                            self.context(plan['personnel_plan_id']))
            except (PersonnelError, OSError) as exc:
                self.db.execute('INSERT INTO module_history(event,occurred_utc,data) VALUES(?,?,?)',
                    ('Crew plan refresh needs source', now(), encode({'version_id': plan['id'], 'reason': str(exc)})))
                continue
            identifier = str(uuid4())
            version = self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM berth_versions WHERE family_id=?',
                                      (plan['family_id'],)).fetchone()[0]
            updated.update(id=identifier, version=version,
                           status='Published' if plan['status'] == 'Published' and not updated['issues'] else 'Draft')
            self.db.execute('INSERT INTO berth_versions VALUES(?,?,?,?,?,?)',
                (identifier, plan['family_id'], version, updated['status'], encode(updated), now()))
            self.db.execute('INSERT INTO module_history(event,occurred_utc,data) VALUES(?,?,?)',
                ('Crew plan refreshed', now(), encode({'before': plan['id'], 'after': identifier})))

    @staticmethod
    def _validate_live_chains(conn, plan_ids=None):
        query, parameters = 'SELECT id,plan_id,payload,status FROM passengers', []
        if plan_ids is not None:
            parameters = sorted(set(plan_ids))
            if not parameters:return
            query += ' WHERE plan_id IN (' + ','.join('?' for _ in parameters) + ')'
        crew = {identifier:(plan_id,json.loads(raw),status) for identifier,plan_id,raw,status in conn.execute(query, parameters)}
        for identifier,(plan_id,record,status) in crew.items():
            if 'person_id' in record and not record['person_id'].strip():
                raise PersonnelError('Invalid personnel identity.')
            # Removed payloads preserve their historical identity/order. Only
            # active references must follow the current parent identity/order.
            if status == 'Cancelled':continue
            previous_id = record.get('previous_task_id')
            if previous_id:
                previous = crew.get(previous_id)
                if (previous is None or previous[0] != plan_id or
                    (previous[1].get('person_id') or previous_id) != (record.get('person_id') or identifier) or
                    previous[1].get('leg_index',1)+1 != record.get('leg_index',1)):
                    raise PersonnelError('The active personnel transfer chain is inconsistent. Review the linked legs before saving.')

    def settings(self):
        return dict(self.db.execute("SELECT key,value FROM module_settings"))

    def context(self, plan_id):
        """Identity and full roster scope, including omitted and removed entries."""
        return {"path":str(self.path),"identity":self.db.execute("SELECT identity FROM module_meta WHERE id=1").fetchone()[0],
                "generation":workspace_files.generation(self.path), "plan_id":plan_id,
                "plan_transfer_vessel": self.settings().get('transfer_vessel_name', ''),
                "scope":digest([dict(r) for r in self.db.execute(
                    "SELECT id,version,status FROM passengers WHERE plan_id=? ORDER BY id",(plan_id,))])}

    def assert_context(self, context):
        if context != self.context(context.get("plan_id")):
            raise PersonnelError("The crew list or database changed. Reopen the draft before saving.")

    @staticmethod
    def port_name(snapshot):
        """Cargo Settings owns the one port; module_settings.port_name is a legacy import alias."""
        return next((r["name"] for r in snapshot["locations"] if r["kind"]=="SHORE"), "xx port")

    def set_setting(self, name, value):
        if name not in {"port_name", "transfer_vessel_name", "backup_directory"}:
            raise PersonnelError("Unknown personnel setting.")
        value = text(value)
        if name == "port_name" and not value:
            raise PersonnelError("Port name is required.")
        if len(value) > 1000:
            raise PersonnelError("Setting value is too long.")
        self.db.execute("INSERT OR REPLACE INTO module_settings VALUES(?,?)", (name, value))

    def update_settings(self, values):
        with self.atomic():
            for name,value in values.items():
                self.set_setting(name,value)
        return self.settings()

    def create_plan(self, name, plan_date, identifier=None):
        if not text(name) or not iso_date(plan_date):
            raise PersonnelError("Enter a plan name and a valid date.")
        if len(text(name))>200:raise PersonnelError('Crew list name must contain at most 200 characters.')
        identifier = identifier or str(uuid4())
        self.db.execute("INSERT INTO personnel_plans VALUES(?,?,?,?)", (identifier, text(name), iso_date(plan_date), now()))
        return identifier

    def rename_plan(self, identifier, name, expected_name):
        name=text(name)
        if not name or len(name)>200:raise PersonnelError('Enter a crew list name containing 1–200 characters.')
        with self.atomic():
            old=self.db.execute('SELECT name FROM personnel_plans WHERE id=?',(identifier,)).fetchone()
            if old is None:raise PersonnelError('This crew list no longer exists. Refresh the list.')
            if old['name']!=expected_name:raise PersonnelError('The crew list name changed. Refresh before renaming it.')
            self.db.execute('UPDATE personnel_plans SET name=? WHERE id=?',(name,identifier))
            self.db.execute('INSERT INTO module_history(event,occurred_utc,data) VALUES(?,?,?)',
                            ('Crew list renamed',now(),encode({'plan_id':identifier,'before':old['name'],'after':name})))
        return identifier

    def plans(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM personnel_plans ORDER BY created_utc DESC")]

    def passengers(self, plan_id):
        return [dict(r) | json.loads(r["payload"]) for r in self.db.execute(
            "SELECT * FROM passengers WHERE plan_id=? ORDER BY rowid", (plan_id,))]

    def passenger(self, identifier):
        row = self.db.execute("SELECT * FROM passengers WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise PersonnelError("This passenger task no longer exists.")
        return dict(row) | json.loads(row["payload"])

    def history(self, identifier):
        return [dict(r) for r in self.db.execute("SELECT * FROM personnel_history WHERE task_id=? ORDER BY id", (identifier,))]

    def _event(self, identifier, event, before=None, after=None, reason=""):
        self.db.execute("INSERT INTO personnel_history(task_id,event,occurred_utc,reason,data) VALUES(?,?,?,?,?)",
                        (identifier, event, now(), text(reason), encode({"before": before, "after": after})))

    def add_passenger(self, plan_id, record, validate=True):
        data = clean_payload(personnel_record(record))
        if not text(data.get("name")):
            raise PersonnelError("Passenger name is required.")
        if validate:
            self._validate_route(data)
        identifier = str(uuid4())
        with self.atomic():
            self._insert(identifier, plan_id, data)
        return identifier

    def _insert(self, identifier, plan_id, data):
        data = clean_payload(personnel_record(data))
        data.setdefault('person_id', identifier)
        data['leg_index'] = leg_order(data)
        self.db.execute("INSERT INTO passengers(id,plan_id,payload,status,created_utc) VALUES(?,?,?,'Waiting',?)",
                        (identifier, plan_id, encode(data), now()))
        self._event(identifier, "Created", after=data)

    def planning_source(self, snapshot):
        """Keep Cargo dependency settings intact while resolving the Personnel override."""
        result = dict(snapshot)
        result['plan_transfer_vessel'] = self.settings().get('transfer_vessel_name', '').strip() or snapshot['settings'].get('transfer_vessel_name', '')
        return result

    def add_next_leg(self, identifier, record, snapshot, expected_version):
        old = self.passenger(identifier)
        if old['version'] != expected_version or old['status'] == 'Cancelled':
            raise PersonnelError('This crew entry changed. Refresh before adding a leg.')
        data = self.bind_record(record, snapshot)
        self._validate_route(data)
        if key(data['name']) != key(old['name']):
            raise PersonnelError('The next leg must belong to the same person.')
        if data['from_id'] != old.get('to_id'):
            raise PersonnelError('The next leg must start at the preceding destination.')
        data.update(person_id=person_identity(old), leg_index=leg_order(old) + 1, previous_task_id=identifier)
        return self._add_linked_leg(old, data)

    def _add_linked_leg(self, old, data):
        identifier = str(uuid4())
        with self.atomic():
            fresh = self.passenger(old['id'])
            if fresh['version'] != old['version']:
                raise PersonnelError('The preceding leg changed. Refresh before saving.')
            if any(r.get('previous_task_id') == old['id'] for r in self.passengers(old['plan_id']) if r['status'] != 'Cancelled'):
                raise PersonnelError('This person already has a next leg. Edit that leg or continue from its last leg.')
            self._insert(identifier, old['plan_id'], data)
            self._event(identifier, 'Next transfer leg linked', after={'previous_task_id': old['id'], 'person_id': data['person_id']})
        return identifier

    def link_crew_legs(self, identifiers, expected):
        """User-confirmed association of existing rows, in the selected leg order."""
        identifiers = list(dict.fromkeys(identifiers))
        if len(identifiers) < 2:
            raise PersonnelError('Select at least two crew entries in their transfer order.')
        with self.atomic():
            records = [self.passenger(i) for i in identifiers]
            root = records[0]
            if root.get('previous_task_id') in identifiers:
                raise PersonnelError('Keep the preceding leg first; a person cannot have a circular transfer chain.')
            if any(r['version'] != expected.get(r['id']) or r['status'] == 'Cancelled' for r in records):
                raise PersonnelError('A crew entry changed. Refresh before linking.')
            if any(r['plan_id'] != root['plan_id'] or key(r['name']) != key(root['name']) for r in records):
                raise PersonnelError('Only entries for the same person in one crew list can be linked.')
            linked_ids = set(identifiers)
            if any(r['id'] not in linked_ids and r.get('previous_task_id') in linked_ids and r['status'] != 'Cancelled'
                   for r in self.passengers(root['plan_id'])):
                raise PersonnelError('Include the existing next legs when relinking this person.')
            for previous, current in zip(records, records[1:]):
                if not previous.get('to_id') or previous['to_id'] != current.get('from_id'):
                    raise PersonnelError('Each next leg must start at the preceding destination.')
            for offset, current in enumerate(records[1:], 1):
                data = clean_payload(current)
                data.update(person_id=person_identity(root), leg_index=leg_order(root) + offset,
                            previous_task_id=records[offset - 1]['id'])
                self.db.execute('UPDATE passengers SET payload=?,version=version+1 WHERE id=?', (encode(data), current['id']))
                self._event(current['id'], 'Crew legs linked', before=clean_payload(current), after=data)
        return identifiers

    @staticmethod
    def _validate_route(data):
        for field in ("name", "position", "date", "from_id", "to_id"):
            if field == 'from_id' and data.get('from_signature', '').startswith('transfer:') and data.get('from_name'):
                continue
            if not data.get(field):
                raise PersonnelError(f"Missing {field}. Edit this task before executing it.")
        if not iso_date(data["date"]):
            raise PersonnelError("Enter a valid transfer date.")
        if data["from_id"] == data["to_id"]:
            raise PersonnelError("From and To must be different locations.")
        if data.get("issues"):
            raise PersonnelError("Resolve the import issues before executing this task.")

    def edit_passenger(self, identifier, record, expected_version, reason=""):
        old = self.passenger(identifier)
        if old["version"] != expected_version:
            raise PersonnelError("This task changed. Refresh before saving.")
        if old["status"] in {"Done", "Cancelled"}:
            raise PersonnelError("Finished tasks are read-only. Correct the status with a reason first.")
        data = clean_payload(personnel_record(record))
        self._validate_route(data)
        if old["status"] == "On Board":
            if not text(reason):
                raise PersonnelError("Explain the destination adjustment.")
            for field in ("name", "position", "nationality", "from_id", "date"):
                if data.get(field) != old.get(field):
                    raise PersonnelError("An on-board task only allows destination or comment changes.")
        with self.atomic():
            changed=self.db.execute("UPDATE passengers SET payload=?,version=version+1 WHERE id=? AND version=?", (encode(data), identifier,expected_version)).rowcount
            if changed!=1:raise PersonnelError('This task changed. Refresh before saving.')
            self._event(identifier, "Destination changed" if old["status"] == "On Board" else "Edited",
                        before=clean_payload(old), after=data, reason=reason)

    def transition(self, identifiers, target, timezone="Asia/Riyadh", reason="", correction=False, expected=None):
        identifiers = list(dict.fromkeys(identifiers))
        if not identifiers:
            raise PersonnelError("Select at least one passenger.")
        if target not in {"Waiting", "On Board", "Done", "Cancelled"}:
            raise PersonnelError("Choose a valid personnel status.")
        stamp = now()
        local_date = datetime.fromisoformat(stamp).astimezone(ZoneInfo(timezone)).date().isoformat()
        with self.atomic():
            for identifier in identifiers:
                old = self.passenger(identifier)
                if expected is not None and old["version"] != expected.get(identifier):
                    raise PersonnelError("A selected task changed. Refresh the passenger list.")
                if old["status"] == target:
                    raise PersonnelError("A selected task already has this status.")
                if target == "Cancelled" and old["status"] != "Waiting":
                    raise PersonnelError("Only Waiting tasks can be cancelled. Resolve on-board passengers first.")
                if correction:
                    if not text(reason):
                        raise PersonnelError("A correction reason is required.")
                elif (old["status"], target) not in {("Waiting", "On Board"), ("On Board", "Done"), ("Waiting", "Cancelled")}:
                    raise PersonnelError("Use a status correction with a reason for this change.")
                if target in {"On Board", "Done"}:
                    self._validate_route(old)
                pickup = old["pickup_utc"] if target in {"On Board", "Done"} else None
                if target == "On Board":
                    pickup = stamp
                self.db.execute("UPDATE passengers SET status=?,pickup_utc=?,drop_utc=?,completed_date=?,version=version+1 WHERE id=?",
                                (target, pickup, stamp if target == "Done" else None,
                                 local_date if target == "Done" else None, identifier))
                self._event(identifier, "Corrected" if correction else target,
                            before={"status": old["status"], "pickup_utc": old["pickup_utc"], "drop_utc": old["drop_utc"]},
                            after={"status": target, "at": stamp, "timezone": timezone}, reason=reason)

    def set_alias(self, snapshot, alias, vessel_id):
        location = next((r for r in snapshot["locations"] if r["id"] == vessel_id and r["active"]), None)
        if location is None:
            raise PersonnelError("Choose an active Fleet vessel.")
        self.db.execute("INSERT OR REPLACE INTO vessel_aliases VALUES(?,?,?,?)",
                        (snapshot.get('ledger_identity') or snapshot["source_path"], key(alias), vessel_id, location_signature(location)))

    def resolve_location(self, snapshot, label):
        label_key = key(label)
        if not label_key:
            return None
        locations = [r for r in snapshot["locations"] if r["active"]]
        port = key(self.port_name(snapshot))
        if label_key in {port, key(self.settings().get("port_name")), "xxport", "xx port", "on shore", "port", "shore"}:
            return next((r for r in locations if r["kind"] == "SHORE"), None)
        exact = [r for r in locations if key(r["name"]) == label_key]
        if len(exact) == 1:
            return exact[0]
        preview_id=snapshot.get('preview_aliases',{}).get(label_key)
        if preview_id is not None:
            return next((r for r in locations if r['id']==preview_id),None)
        alias = self.db.execute("SELECT * FROM vessel_aliases WHERE source_path=? AND alias=?",
                                (snapshot.get('ledger_identity') or snapshot["source_path"], label_key)).fetchone()
        if alias is None:
            # Older aliases were keyed by path; retain them only with the recorded Fleet signature.
            alias=self.db.execute('SELECT * FROM vessel_aliases WHERE source_path=? AND alias=?',
                                  (snapshot['source_path'],label_key)).fetchone()
        if alias:
            return next((r for r in locations if r["id"] == alias["vessel_id"] and location_signature(r) == alias["signature"]), None)
        # Unambiguous Fleet abbreviations are shown in the import review, never merged by person name.
        import re
        vessels = [r for r in locations if r['kind'] == 'VESSEL']
        compact = lambda value: re.sub(r'[\W_]+', '', key(value))
        same = [r for r in vessels if compact(r['name']) == compact(label)]
        if same:
            return same[0] if len(same) == 1 else None
        # Established short names used by the BGP crew-change workbooks. Match
        # the full active Fleet name, never a hard-coded location ID.
        full_name = {'bvc': 'bgp victor', 'spr': 'bgp spirit', 'bgp inv': 'bgp innovator'}.get(label_key)
        if full_name:
            same = [r for r in vessels if key(r['name']) == full_name]
            return same[0] if len(same) == 1 else None
        tokens = re.findall(r'[\w]+', label_key)
        if len(tokens) > 1 and all(len(token) >= 3 for token in tokens):
            same = [r for r in vessels if len(parts := re.findall(r'[\w]+', key(r['name']))) == len(tokens)
                    and all(part.startswith(token) for token, part in zip(tokens, parts))]
            if same:
                return same[0] if len(same) == 1 else None
        if len(label_key) >= 3:
            candidates = [r for r in locations if r["kind"] == "VESSEL" and any(
                word.startswith(label_key) for word in re.findall(r"[\w]+", key(r["name"])))]
            if len(candidates) == 1:
                return candidates[0]
        return None

    def crew_records(self, plan_id, snapshot):
        """Resolve imported crew routes independently of legacy execution status."""
        snapshot = self.planning_source(snapshot)
        port = self.port_name(snapshot)
        shore = next((r["id"] for r in snapshot["locations"] if r["kind"] == "SHORE"), None)
        records = []
        for row in self.passengers(plan_id):
            if row["status"] == "Cancelled":
                continue
            raw = dict(row)
            if row.get("batch_id") and not row.get('text_case'):
                # Legacy read-time compatibility without overwriting confirmed spelling.
                raw = legacy_personnel(raw)
            if row.get("direction") == "Sign-on" or row.get("from_id") == shore:
                raw["from_name"] = port
                raw["to_name"] = crew_vessel_name(row, 'to')
            elif row.get("direction") == "Sign-off" or row.get("to_id") == shore:
                raw["from_name"] = crew_vessel_name(row, 'from')
                raw["to_name"] = port
            rebound = self.bind_record(raw, snapshot)
            record = {**row, **rebound, "status": "Waiting", "kind": "Passengers"}
            record['leg_index']=leg_order(record)
            for side in ("from", "to"):
                location = next((r for r in snapshot["locations"] if r["id"] == record.get(side + "_id")), None)
                if location:
                    record[side + "_name"] = port if location["kind"] == "SHORE" else location["name"]
            records.append(record)
        return records

    def edit_crew_entry(self, identifier, record, expected_version):
        old = self.passenger(identifier)
        if old["version"] != expected_version:
            raise PersonnelError("This crew entry changed. Refresh before saving.")
        data = clean_payload(personnel_record(record))
        for field in ('person_id', 'leg_index', 'previous_task_id'):
            if field in old:
                data[field] = old[field]
        self._validate_route(data)
        with self.atomic():
            changed=self.db.execute("UPDATE passengers SET payload=?,version=version+1 WHERE id=? AND version=?", (encode(data), identifier,expected_version)).rowcount
            if changed!=1:raise PersonnelError('This crew entry changed. Refresh before saving.')
            self._event(identifier, "Crew entry edited", before=clean_payload(old), after=data)

    def text_case_preview(self, plan_id):
        changes = []
        for row in self.passengers(plan_id):
            if row['status'] == 'Cancelled':
                continue
            suggested = legacy_personnel(row)
            for field in ('name', 'position'):
                if row.get(field, '') != suggested.get(field, ''):
                    changes.append({'id': row['id'], 'version': row['version'], 'field': field,
                        'label': f"{row.get('name', '')} / {field}", 'before': row.get(field, ''),
                        'after': suggested[field], 'review': suggested['text_case'][field]['review']})
        return changes

    def apply_text_case(self, plan_id, changes):
        if not changes:
            raise PersonnelError('Select at least one spelling change.')
        with self.atomic():
            available = {(p['id'], p['field']): p for p in self.text_case_preview(plan_id)}
            grouped = {}
            for change in changes:
                token = (change.get('id'), change.get('field'))
                if available.get(token) != change:
                    raise PersonnelError('Crew entries changed. Reopen the spelling preview.')
                if token in grouped:
                    raise PersonnelError('A spelling change was selected twice.')
                grouped[token] = change
            for identifier in dict.fromkeys(p['id'] for p in changes):
                old = self.passenger(identifier)
                data = clean_payload(old)
                proposal = legacy_personnel(old)
                data['text_case'] = dict(data.get('text_case', {}))
                for field in ('name', 'position'):
                    if (identifier, field) in grouped:
                        data[field] = proposal[field]
                        data['text_case'][field] = proposal['text_case'][field]
                    elif proposal.get('text_case',{}).get(field,{}).get('preserve'):
                        data['text_case'][field] = proposal['text_case'][field]
                self.db.execute('UPDATE passengers SET payload=?,version=version+1 WHERE id=?', (encode(data), identifier))
                self._event(identifier, 'Name casing normalized', before=clean_payload(old), after=data)
        return len(changes)

    def remove_crew_entries(self, versions):
        with self.atomic():
            for identifier, version in versions.items():
                old = self.passenger(identifier)
                if old["version"] != version:
                    raise PersonnelError("A crew entry changed. Refresh before removing it.")
                self.db.execute("UPDATE passengers SET status='Cancelled',version=version+1 WHERE id=?", (identifier,))
                self._event(identifier, "Removed from crew list", before=clean_payload(old))

    def bind_record(self, record, snapshot, plan_date=None):
        snapshot = self.planning_source(snapshot)
        data = clean_payload(record)
        if plan_date:
            data["date"] = iso_date(plan_date)
        direction = data.get("direction", "Transfer")
        port = self.port_name(snapshot)
        if direction == "Sign-on":
            source, target = port, crew_vessel_name(data, 'to')
        elif direction == "Sign-off":
            source, target = crew_vessel_name(data, 'from'), port
        else:
            source, target = data.get("from_name", ""), data.get("to_name", "")
        data.update(from_name=source, to_name=target, source_path=snapshot["source_path"])
        issues = [f"Missing {f}" for f in ("name", "position", "date") if not data.get(f)]
        for side, label in (("from", source), ("to", target)):
            location = self.resolve_location(snapshot, label)
            data[side + "_id"] = location["id"] if location else None
            data[side + "_signature"] = location_signature(location) if location else ""
            if side == 'from' and location is None and transfer_origin(data, snapshot):
                data['from_signature'] = 'transfer:' + key(transfer_name(snapshot))
            if location is None and not (side == 'from' and transfer_origin(data, snapshot)):
                issues.append(f"Unmatched {side}: {label or '(empty)'}")
        issues.extend(i for i in record.get("issues", []) if i.startswith("Formula"))
        if data.get("from_id") and data["from_id"] == data.get("to_id"):
            issues.append("From and To are the same")
        shore = next((r["id"] for r in snapshot["locations"] if r["kind"] == "SHORE"), None)
        if shore is not None and data.get('from_id') == shore:
            data['direction'] = 'Sign-on'
        elif shore is not None and data.get('to_id') == shore:
            data['direction'] = 'Sign-off'
        elif data.get('from_id') and data.get('to_id'):
            data['direction'] = 'Transfer'
        data["issues"] = issues
        return data

    def route_issues(self, record, snapshot):
        issues = list(record.get("issues", []))
        if record.get("source_path") != snapshot["source_path"]:
            issues.append("Cargo database changed; remap this task")
        for side in ("from", "to"):
            location = next((r for r in snapshot["locations"] if r["id"] == record.get(side + "_id")), None)
            if side == 'from' and transfer_origin(record, self.planning_source(snapshot)):
                continue
            if location is None or not location["active"] or location_signature(location) != record.get(side + "_signature"):
                issues.append(f"{side.title()} location changed; remap this task")
        return list(dict.fromkeys(issues))

    def import_preview(self, parsed, snapshot, plan_id, mode="append", plan_date=None, crew_list=False):
        if mode not in {"new", "append", "replace"}:
            raise PersonnelError("Choose an import mode.")
        if mode != "new" and not any(p["id"] == plan_id for p in self.plans()):
            raise PersonnelError("Choose the personnel plan to update.")
        new_plan_id=str(uuid4()) if mode=='new' else None
        signature=self._import_signature(parsed,new_plan_id or plan_id,mode)
        if mode == "replace":
            signature=digest([signature,self.context(plan_id)["scope"]])
        if mode != "new" and self.db.execute("SELECT 1 FROM import_keys WHERE signature=?",(signature,)).fetchone():
            raise PersonnelError("This worksheet and column mapping have already been imported into this crew list.")
        if mode == "append" and self.db.execute("""SELECT 1 FROM import_batches b WHERE file_hash=? AND sheet=? AND plan_id=?
            AND mode='append' AND NOT EXISTS(SELECT 1 FROM import_keys k WHERE k.batch_id=b.id)""",
            (parsed["file_hash"],parsed["sheet"],plan_id)).fetchone():
            raise PersonnelError("This worksheet has already been imported. Review the existing plan.")
        previous = self.passengers(plan_id) if plan_id else []
        previous_by_id = {row['id']: row for row in previous}
        previous_by_name = {}
        for row in previous:
            previous_by_name.setdefault(key(row.get('name')), []).append(row)
        items = []
        for record in parsed["records"]:
            data = self.bind_record(record, snapshot, plan_date)
            explicit = record.get("task_id")
            candidates = []
            if explicit:
                candidates = [previous_by_id[explicit]] if explicit in previous_by_id else []
            elif mode != "new":
                candidates = previous_by_name.get(key(data.get('name')), [])
            if crew_list and mode == "replace":
                candidates = []
            items.append({"data": data, "candidates": [{"id": r["id"], "name": r["name"], "position": r.get("position", ""),
                           "from_name": r.get("from_name", ""), "to_name": r.get("to_name", ""), "date": r.get("date", ""),
                           "status": r["status"]} for r in candidates], "match_id": None})
        return {"parsed": {k: parsed[k] for k in ("file_name", "file_hash", "content_hash", "sheet", "mapping_hash", "parser_version") if k in parsed},
                "plan_id": plan_id, "new_plan_id":new_plan_id, "mode": mode, "items": items, "crew_list": crew_list,
                "expected_versions": {r["id"]: r["version"] for r in previous},
                "source_hash": snapshot["source_hash"], "import_signature":signature,
                "similar_file": bool(self.db.execute("SELECT 1 FROM import_batches WHERE content_hash=?", (parsed["content_hash"],)).fetchone())}

    @staticmethod
    def _import_signature(parsed,plan_id,mode):
        return digest({"file":parsed["file_hash"],"sheet":parsed["sheet"],"mapping":parsed.get("mapping_hash",digest(parsed.get("blocks",[]))),
                       "parser":parsed.get("parser_version",1),"plan":plan_id,"mode":mode})

    def commit_import(self, preview, plan_name="", plan_date="", cancel_missing=False):
        if preview["mode"] == "replace" and cancel_missing and any(not text(item["data"].get("name")) for item in preview["items"]):
            raise PersonnelError("Resolve unnamed rows before cancelling missing tasks in a complete replacement. Append can retain them for review.")
        batch_id = str(uuid4())
        with self.atomic():
            plan_id = preview["plan_id"]
            for alias,vessel_id in preview.get('aliases',{}).get('values',{}).items():
                self.set_alias(preview['aliases']['source'],alias,vessel_id)
            if preview["mode"] == "new":
                if self.db.execute('SELECT 1 FROM import_keys WHERE signature=?',(preview.get('import_signature'),)).fetchone():
                    raise PersonnelError('This reviewed import was already saved. Preview a new list to import again.')
                plan_id = self.create_plan(plan_name, plan_date,preview.get('new_plan_id'))
            old_rows = {r["id"]: r for r in self.passengers(plan_id)}
            if preview["mode"] != "new" and {i: r["version"] for i, r in old_rows.items()} != preview["expected_versions"]:
                raise PersonnelError("The target plan changed. Preview the import again.")
            matched = [item["match_id"] for item in preview["items"] if item.get("match_id")]
            if len(matched) != len(set(matched)):
                raise PersonnelError("Two imported rows cannot update the same task. Resolve the row matches.")
            self.db.execute("INSERT INTO import_batches VALUES(?,?,?,?,?,?,?,?)", (batch_id, plan_id,
                            preview["parsed"]["file_name"], preview["parsed"]["file_hash"], preview["parsed"]["content_hash"],
                            preview["parsed"]["sheet"], preview["mode"], now()))
            signature=preview.get("import_signature") or self._import_signature(preview["parsed"],plan_id,preview["mode"])
            try:
                self.db.execute("INSERT INTO import_keys VALUES(?,?)",(signature,batch_id))
            except sqlite3.IntegrityError as exc:
                raise PersonnelError("This reviewed import was already saved. Refresh the preview.") from exc
            added, updated, protected = 0, 0, []
            for item in preview["items"]:
                data = clean_payload(item["data"])
                data["batch_id"] = batch_id
                match_id = item.get("match_id")
                if match_id:
                    old = old_rows.get(match_id)
                    if old is None:
                        raise PersonnelError("Choose a task from the target personnel plan.")
                    for field in ('person_id', 'leg_index', 'previous_task_id'):
                        if field in old:
                            data[field] = old[field]
                    if old["status"] != "Waiting" and not preview.get("crew_list"):
                        protected.append(old["name"])
                        self._event(match_id, "Import change requires review", after=data)
                        continue
                    self.db.execute("UPDATE passengers SET payload=?,version=version+1 WHERE id=?", (encode(data), match_id))
                    if preview.get("crew_list"):
                        self.db.execute("UPDATE passengers SET status='Waiting' WHERE id=?", (match_id,))
                    self._event(match_id, "Import updated", before=clean_payload(old), after=data)
                    updated += 1
                else:
                    self._insert(str(uuid4()), plan_id, data)
                    added += 1
            cancelled = 0
            if preview["mode"] == "replace" and cancel_missing:
                for identifier, old in old_rows.items():
                    if identifier not in matched and (old["status"] == "Waiting" or preview.get("crew_list")):
                        self.db.execute("UPDATE passengers SET status='Cancelled',version=version+1 WHERE id=?", (identifier,))
                        self._event(identifier, "Removed from crew list" if preview.get("crew_list") else "Cancelled", reason="Confirmed missing from complete replacement list")
                        cancelled += 1
                    elif identifier not in matched and old["status"] in {"On Board", "Done"}:
                        protected.append(old["name"])
            if preview.get("crew_list") and iso_date(plan_date):
                self.db.execute("UPDATE personnel_plans SET date=? WHERE id=?", (iso_date(plan_date), plan_id))
            return {"plan_id": plan_id, "added": added, "updated": updated, "cancelled": cancelled, "protected": protected}

    def save_berth(self, draft, published=False, family_id=None):
        validate_plan_shape(draft)
        if published:
            from .berth_optimization_validation import validate_saved_plan
            validate_saved_plan(draft)
        elif draft.get('transport_contract') is not None:
            from .berth_optimization_validation import validate_contract
            validate_contract(draft['transport_contract'])
        if published and draft.get("issues"):
            raise PersonnelError("Resolve all plan issues before publishing. You can save a Draft version.")
        needs_live_check=published and (draft.get('transport_contract') or not draft.get("base_version_id") or draft.get("revision_reviewed"))
        if needs_live_check:
            from .personnel_cargo import read_cargo, dependency_hash
            dependencies=draft.get("source_dependencies")
            current=read_cargo(draft["source_path"], selected_cargo=dependencies["cargo_ids"] if dependencies else None)
            if ((dependency_hash(current,dependencies)!=draft.get("dependency_hash")) if dependencies
                else current["source_hash"]!=draft["source_hash"]):
                raise PersonnelError("Cargo sources changed. Regenerate the draft before publishing.")
            if draft.get('transport_contract'):
                from .berth_optimizer import make_problem
                from .berth_plan import cargo_tasks
                contract=draft['transport_contract']
                exclusions={k for k,v in draft.get('task_selections',{}).items() if v.get('state')=='user_excluded'}
                material_ids=[int(t['key'].split(':',1)[1]) for t in contract['tasks'] if t['key'].startswith('Materials:')]
                planning=self.planning_source(current)
                actual=make_problem(planning,self.crew_records(draft['personnel_plan_id'],planning),cargo_tasks(planning,material_ids),
                                    excluded=exclusions,pins=contract['pins'],locked=contract['locked'],reference_order=contract.get('reference_order',[]))
                if actual['hash']!=contract['hash']:
                    raise PersonnelError('The automatic transport scope or initial conditions changed. Replan before publishing.')
        payload = json.loads(encode(draft))
        family = family_id or str(uuid4())
        identifier = str(uuid4())
        with self.atomic():
            version = self.db.execute("SELECT COALESCE(MAX(version),0)+1 FROM berth_versions WHERE family_id=?", (family,)).fetchone()[0]
            if draft.get("personnel_context"):
                self.assert_context(draft["personnel_context"])
            if needs_live_check:
                versions=draft.get('personnel_versions',{})
                for crew_id,expected in versions.items():
                    if self.passenger(crew_id)['version']!=expected:
                        raise PersonnelError('Personnel changed. Regenerate the draft before publishing.')
                if draft.get('personnel_plan_id'):
                    active={r[0] for r in self.db.execute("SELECT id FROM passengers WHERE plan_id=? AND status!='Cancelled'",(draft['personnel_plan_id'],))}
                    if not active<=set(versions):
                        raise PersonnelError('The full crew-list scope changed or is incomplete. Regenerate the draft before publishing.')
            payload.update(id=identifier, family_id=family, version=version, status="Published" if published else "Draft")
            self.db.execute("INSERT INTO berth_versions VALUES(?,?,?,?,?,?)",
                            (identifier, family, version, payload["status"], encode(payload), now()))
        return payload

    def berth_versions(self, include_removed=False):
        clause='' if include_removed else ' WHERE id NOT IN (SELECT version_id FROM removed_berth_history)'
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM berth_versions'+clause+' ORDER BY created_utc DESC,version DESC')]

    def berth_summaries(self):
        return version_summaries(self.db)

    def berth_version(self, identifier):
        return version_payload(self.db, identifier)

    def latest_berth(self, family_id):
        return latest_family_payload(self.db, family_id)

    def clear_berth_history(self, identifiers):
        identifiers=list(dict.fromkeys(identifiers))
        if not identifiers:raise PersonnelError('Select at least one saved version to remove.')
        with self.atomic():
            available={r['id'] for r in version_summaries(self.db)}
            if not set(identifiers)<=available:raise PersonnelError('Version history changed. Refresh before removing versions.')
            self.db.executemany('INSERT INTO removed_berth_history VALUES(?,?)',[(i,now()) for i in identifiers])
            self.db.execute('INSERT INTO module_history(event,occurred_utc,data) VALUES(?,?,?)',
                            ('Berthing history cleared',now(),encode({'version_ids':identifiers})))
        return identifiers

    @staticmethod
    def validate_file(path):
        conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
                raise PersonnelError("Personnel database integrity check failed.")
            meta = conn.execute("SELECT version,identity FROM module_meta WHERE id=1").fetchone()
            if meta is None or meta[0] != 1 or not isinstance(meta[1],str) or not meta[1].strip():
                raise PersonnelError("Choose a supported personnel backup, not a Cargo backup.")
            reference=sqlite3.connect(":memory:")
            try:
                reference.executescript(DDL)
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='import_keys'").fetchone():
                    reference.executescript(IMPORT_DDL)
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name IN ('removed_berth_history','module_history')").fetchone():
                    reference.executescript(MANAGEMENT_DDL)
                allowed_executable = set(reference.execute(
                    "SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view')"))
                for schema_object in conn.execute(
                        "SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view')"):
                    if schema_object not in allowed_executable:
                        raise PersonnelError("Personnel backup contains an unsupported trigger or view.")
                for kind,name,sql in reference.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"):
                    actual=conn.execute("SELECT sql FROM sqlite_master WHERE type=? AND name=?",(kind,name)).fetchone()
                    normalize=lambda value:''.join(value.casefold().split()).replace('ifnotexists','')
                    if actual is None or (sql and normalize(actual[0] or '') != normalize(sql)):
                        raise PersonnelError(f"Personnel backup is missing or has an invalid schema object: {name}.")
                    if kind=='table' and list(conn.execute(f'PRAGMA table_info("{name}")')) != list(reference.execute(f'PRAGMA table_info("{name}")')):
                        raise PersonnelError(f"Invalid personnel table columns: {name}.")
            finally:
                reference.close()
            settings=dict(conn.execute("SELECT key,value FROM module_settings"))
            if not text(settings.get("port_name")) or any(not isinstance(v,str) or len(v)>1000 for v in settings.values()):
                raise PersonnelError("Personnel backup settings are incomplete or invalid.")
            list(conn.execute("SELECT * FROM personnel_plans ORDER BY created_utc DESC"))
            # A valid SQLite file also needs usable, whitelisted application payloads.
            for (raw,) in conn.execute("SELECT payload FROM passengers"):
                record = json.loads(raw)
                if (not isinstance(record, dict) or not isinstance(record.get("issues",[]),list)
                    or any(not isinstance(p,str) for p in record.get('issues',[]))
                    or any(not isinstance(record[f],str) for f in ('name','position','nationality','date','source_date','direction','vessel',
                            'comment','from_name','to_name','source_path','from_signature','to_signature','source_sheet','batch_id',
                            'person_id','previous_task_id') if f in record)
                    or ('leg_index' in record and (type(record['leg_index']) is not int or record['leg_index'] < 1))
                    or any(record.get(f) is not None and (type(record[f]) is not int or record[f]<=0) for f in ('from_id','to_id'))
                    or any(not isinstance(record.get(k,{}),dict) for k in ('original_values','source_cells'))
                    or record != clean_payload(record)):
                    raise PersonnelError("This backup contains unsupported personnel fields.")
            for identifier,version,status,raw in conn.execute('SELECT id,version,status,payload FROM berth_versions'):
                value=json.loads(raw)
                if not isinstance(value,dict) or (value.get('id'),value.get('version'),value.get('status'))!=(identifier,version,status):
                    raise PersonnelError('Berthing plan version metadata is inconsistent.')
                validate_plan_shape(value)
                if value.get('transport_contract') is not None:
                    from .berth_optimization_validation import validate_saved_plan,validate_contract
                    validate_contract(value['transport_contract'])
                    if status=='Published':validate_saved_plan(value)
            PersonnelService._validate_live_chains(conn)
            for (version,) in conn.execute('SELECT version FROM passengers'):
                if type(version) is not int or version<0:
                    raise PersonnelError('Invalid crew entry version.')
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise PersonnelError("Choose a valid personnel backup.") from exc
        finally:
            conn.close()

    def inspect_backup(self,path):
        self.validate_file(path)
        conn=sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
        try:
            return {"module":"Personnel", "path":str(Path(path).resolve()),
                    "identity":conn.execute("SELECT identity FROM module_meta WHERE id=1").fetchone()[0],
                    "crew_entries":conn.execute("SELECT count(*) FROM passengers WHERE status!='Cancelled'").fetchone()[0],
                    "plan_versions":conn.execute("SELECT count(*) FROM berth_versions").fetchone()[0],
                    "modified":datetime.fromtimestamp(Path(path).stat().st_mtime,UTC).isoformat()}
        finally:conn.close()

    def _check_output(self,target):
        try:workspace_files.check_output(target,self.path)
        except ProtectedFileError as exc:raise PersonnelError(str(exc)) from exc

    def backup(self, destination):
        target = Path(destination).resolve()
        self._check_output(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + "." + str(uuid4()) + ".tmp")
        try:
            out = sqlite3.connect(temp)
            try:
                self.db.backup(out)
            finally:
                out.close()
            self.validate_file(temp)
            self._check_output(target)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return str(target)

    def restore(self, candidate):
        candidate = Path(candidate).resolve()
        if candidate == self.path:
            raise PersonnelError("Choose a separate backup file.")
        self.validate_file(candidate)
        safety = self.path.with_name(f"personnel-before-restore-{uuid4().hex}.sqlite3")
        self.backup(safety)
        source = sqlite3.connect(candidate.as_uri() + "?mode=ro", uri=True)
        try:
            source.backup(self.db)
            self.validate_file(self.path)
            self.db.executescript(IMPORT_DDL)
            self.db.executescript('BEGIN IMMEDIATE;'+MANAGEMENT_DDL+'COMMIT;')
            self.db.executescript(INDEX_DDL + CHANGE_TRACKING_DDL)
        except Exception as restore_error:
            rollback = None
            try:
                rollback = sqlite3.connect(safety.as_uri()+"?mode=ro",uri=True)
                rollback.backup(self.db)
                self.validate_file(self.path)
            except Exception as recovery_error:
                self.maintenance=True
                self.recovery_files={"safety_copy":str(safety),"candidate":str(candidate),"current":str(self.path)}
                try:self.recovery_marker.write_text(encode(self.recovery_files),encoding='utf-8')
                except OSError as marker_error:self.recovery_files['marker_error']=str(marker_error)
                self.close()
                raise PersonnelError(f"Restore and rollback failed. Writes are blocked. Recover from {safety}. {recovery_error}") from restore_error
            finally:
                if rollback is not None:rollback.close()
            raise
        finally:
            source.close()
        workspace_files.invalidate(self.path)
        return str(safety)

    def relocate(self, destination):
        target = Path(destination).resolve()
        if target == self.path:
            return self
        self._check_output(target)
        if target.exists():
            raise PersonnelError("The target personnel database already exists. Choose another folder.")
        target.parent.mkdir(parents=True, exist_ok=True)
        prepared = target.with_name(target.name + "." + str(uuid4()) + ".tmp")
        created = False
        try:
            self.backup(prepared)
            with target.open("xb") as out:
                created = True
                out.write(prepared.read_bytes())
                out.flush()
                os.fsync(out.fileno())
            result=PersonnelService(target)
            workspace_files.invalidate(self.path)
            return result
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        finally:
            prepared.unlink(missing_ok=True)
