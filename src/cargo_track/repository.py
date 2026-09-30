"""Small SQLite repository. Every mutating caller owns one transaction."""

from __future__ import annotations

import sqlite3


class LedgerRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def leg(self, number: int, *, include_void: bool = True):
        suffix = "" if include_void else " AND is_void=0"
        return self.connection.execute(f"SELECT * FROM transfer_legs WHERE no=?{suffix}", (number,)).fetchone()

    def cargo_legs(self, cargo_id: int, *, include_void: bool = True):
        suffix = "" if include_void else " AND is_void=0"
        return self.connection.execute(f"SELECT * FROM transfer_legs WHERE cargo_id=?{suffix} ORDER BY no", (cargo_id,)).fetchall()

    def current_voyage(self):
        return self.connection.execute("SELECT * FROM voyages WHERE is_current=1").fetchone()

    def current_state(self):
        return self.connection.execute("""SELECT a.data_revision,a.current_voyage_id,a.current_stop_id,
            v.name AS voyage_name,s.vessel_id,s.vessel_name_snapshot,s.position,
            l.name AS vessel_current_name
            FROM app_state a LEFT JOIN voyages v ON v.id=a.current_voyage_id
            LEFT JOIN voyage_stops s ON s.id=a.current_stop_id AND s.removed=0
            LEFT JOIN locations l ON l.id=s.vessel_id WHERE a.id=1""").fetchone()

    def rows(self, where_sql: str, args: list, order_sql: str, limit: int, offset: int):
        return self.connection.execute(f"""SELECT t.*,c.cargo_tag,c.physical_id,
              t.from_name_snapshot AS from_name,t.to_name_snapshot AS to_name,
              f.name AS from_current_name,to_loc.name AS to_current_name,
              f.active AS from_active,to_loc.active AS to_active,
              p.status AS predecessor_status
            FROM transfer_legs t JOIN cargo c ON c.id=t.cargo_id
            JOIN locations f ON f.id=t.from_location_id
            JOIN locations to_loc ON to_loc.id=t.to_location_id
            LEFT JOIN transfer_legs p ON p.no=t.predecessor_no
            WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?""", [*args, limit, offset]).fetchall()

