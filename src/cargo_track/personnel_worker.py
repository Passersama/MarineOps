"""Serial personnel executor; its SQLite connection never leaves its owner thread."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from .personnel_service import PersonnelService


class PersonnelGateway(QObject):
    completed=Signal(str,object,object)

    def __init__(self,path,parent=None):
        super().__init__(parent)
        self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='personnel-db')
        self._callbacks={}
        try:self._service=self._executor.submit(PersonnelService,path).result()
        except Exception:
            self._executor.shutdown(wait=True)
            raise
        self.path=self._service.path
        self.maintenance=False
        self.completed.connect(self._deliver)

    def _invoke(self,name,args,kwargs):
        if self._service.maintenance:
            raise ValueError('Personnel writes are blocked. Recover the preserved safety copy before reopening.')
        result=getattr(self._service,name)(*args,**kwargs)
        if name=='relocate' and result is not self._service:
            old=self._service
            self._service=result
            old.close()
            return str(result.path)
        if name=='relocate':
            return str(self._service.path)
        return result

    def __getattr__(self,name):
        if name.startswith('__'):
            raise AttributeError(name)
        def call(*args,**kwargs):
            return self._executor.submit(self._invoke,name,args,kwargs).result()
        return call

    def submit(self,name,args,callback,failed,kwargs=None):
        request=str(uuid4())
        self._callbacks[request]=(callback,failed)
        future=self._executor.submit(self._invoke,name,args,kwargs or {})
        def finished(future):
            try:value,error=future.result(),None
            except Exception as exc:value,error=None,str(exc)
            self.completed.emit(request,value,error)
        future.add_done_callback(finished)
        return request

    def _deliver(self,request,value,error):
        self.path=self._service.path
        self.maintenance=self._service.maintenance
        callbacks=self._callbacks.pop(request,None)
        if callbacks:
            callbacks[1 if error else 0](error if error else value)

    def close(self):
        self._executor.submit(self._service.close).result()
        self._executor.shutdown(wait=True)
