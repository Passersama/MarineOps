"""A single Qt worker thread owns every application-service connection."""

from __future__ import annotations

import traceback
from PySide6.QtCore import QObject, Signal, Slot

from .domain import AppError, Command
from .service import ApplicationService


class DatabaseWorker(QObject):
    ready=Signal(dict)
    failed=Signal(str,dict)
    result=Signal(str,dict)
    request_failed=Signal(str,dict)
    maintenance=Signal(bool)

    def __init__(self,path):
        super().__init__()
        self.path=str(path)
        self.service=None

    @Slot()
    def open(self):
        try:
            self.service=ApplicationService(self.path)
            self.service.open()
            self.ready.emit(self.service.workspace_snapshot())
        except AppError as error:self.failed.emit(error.message,error.details)
        except Exception as error:self.failed.emit(str(error),{"traceback":traceback.format_exc()})

    @Slot(str,str,dict)
    def request(self,request_id,operation,payload):
        if self.service is None:
            self.request_failed.emit(request_id,{"code":"DATABASE_UNAVAILABLE","message":"The local ledger has not opened yet."})
            return
        try:
            if operation=="_command":
                command=Command(payload["command_id"],payload["operation"],payload["payload"])
                receipt=self.service.handle(command)
                self.result.emit(request_id,{"kind":"receipt","data":{"command_id":receipt.command_id,"operation":receipt.operation,"result":receipt.result,"revision":receipt.revision}})
            elif operation=="_workspace":
                self.result.emit(request_id,{"kind":"workspace","data":self.service.workspace_snapshot()})
            elif operation=="_query":
                view=payload["view"]
                self.result.emit(request_id,{"kind":"query","data":self.service.query_transfers(view,payload.get("filters"),order_column=payload.get("order_column",0),descending=payload.get("descending",False),limit=payload.get("limit",200),offset=payload.get("offset",0))})
            elif operation=="_detail":
                self.result.emit(request_id,{"kind":"detail","data":self.service.transfer_detail(payload["no"],payload.get("include_void",False))})
            elif operation=="_vessels":
                self.result.emit(request_id,{"kind":"vessels","data":self.service.list_vessels()})
            elif operation=="_fleet_details":
                self.result.emit(request_id,{"kind":"fleet_details","data":self.service.list_vessels()})
            elif operation=="_voyage_history":
                self.result.emit(request_id,{"kind":"voyage_history","data":self.service.voyage_history()})
            elif operation=="_cargo_choices":
                self.result.emit(request_id,{"kind":"cargo_choices","data":self.service.cargo_choices()})
            elif operation=="_text_case_preview":
                self.result.emit(request_id,{"kind":"text_case_preview","data":self.service.text_case_preview()})
            elif operation=="_backup_preview":
                self.result.emit(request_id,{"kind":"backup_preview","data":self.service.inspect_backup(payload["path"])})
            elif operation=="_backup":
                self.result.emit(request_id,{"kind":"backup","data":self.service.create_backup(payload["path"])})
            elif operation=="_restore":
                self.maintenance.emit(True)
                try:
                    data=self.service.restore_backup(payload["path"])
                    self.result.emit(request_id,{"kind":"restore","data":data})
                finally:self.maintenance.emit(self.service.connection is None)
            elif operation=="_relocate":
                self.maintenance.emit(True)
                try:
                    old=self.service
                    replacement=old.relocated_service(payload["path"])
                    if replacement is not old:
                        old.close();self.service=replacement;self.path=str(replacement.path)
                    self.result.emit(request_id,{"kind":"relocated","data":{"path":str(self.service.path)}})
                finally:self.maintenance.emit(self.service.connection is None)
            elif operation=="_export":
                data=self.service.export_to(payload["path"],payload["view"],payload.get("filters",{}),payload["format"],payload.get("include_completed",False),order_column=payload.get("order_column",0),descending=payload.get("descending",False))
                self.result.emit(request_id,{"kind":"export","data":data})
            elif operation=="_health":
                self.result.emit(request_id,{"kind":"health","data":self.service.health_report()})
            else:raise AppError("UNKNOWN_QUERY",f"Unknown application request: {operation}")
        except AppError as error:
            self.request_failed.emit(request_id,{"code":error.code,"message":error.message,"details":error.details})
        except Exception as error:
            self.request_failed.emit(request_id,{"code":"INTERNAL_ERROR","message":str(error),"traceback":traceback.format_exc()})
            # Queries are autocommit. On unexpected failure, never let the next request inherit a partial write.
            if self.service.connection is not None and self.service.db.in_transaction:self.service.db.rollback()

    @Slot()
    def shutdown(self):
        if self.service is not None:self.service.close()
        self.service=None
