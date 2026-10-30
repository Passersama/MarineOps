"""Serial personnel executor with asynchronous opening and detached UI reads."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QObject, Signal, Qt
from .personnel_service import PersonnelService
from .personnel_read_model import PersonnelReadModel


class PersonnelGateway(QObject):
    completed=Signal(str,object,object)
    ready=Signal()
    open_failed=Signal(str)
    _WRITES=frozenset(('set_setting','update_settings','create_plan','rename_plan','add_passenger',
        'add_next_leg','link_crew_legs','edit_passenger','transition','set_alias','edit_crew_entry',
        'apply_text_case','remove_crew_entries','commit_import','save_berth','clear_berth_history','restore','relocate'))

    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.path=Path(path).resolve();self.maintenance=False;self._service=None
        self._state={};self._selection=None;self._closed=False;self._executor_stopped=False;self._callbacks={}
        self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='personnel-db')
        self.completed.connect(self._deliver,Qt.ConnectionType.QueuedConnection)
        self._callbacks['open']=(lambda _:self.ready.emit(),self.open_failed.emit)
        future=self._executor.submit(self._open)
        future.add_done_callback(lambda f:self._finished('open',f))

    @property
    def read_model(self):return PersonnelReadModel(self.path,self._state)

    def _open(self):
        self._service=PersonnelService(self.path)
        self._state=self._service.ui_state()

    def _invoke(self,name,args,kwargs):
        if self._service is None:raise ValueError('The Personnel database could not open.')
        if self._service.maintenance:raise ValueError('Personnel writes are blocked. Recover the preserved safety copy before reopening.')
        result=getattr(self._service,name)(*args,**kwargs)
        if name=='relocate':
            if result is not self._service:
                old=self._service;self._service=result;old.close()
            self.path=self._service.path;result=str(self.path)
        if name=='ui_state':
            self._selection=result['plan_id'];self._state=result
        elif name=='prepare_ui':
            self._selection=result['state']['plan_id'];self._state=result['state']
        elif name in self._WRITES:
            self._state=self._service.ui_state(self._selection)
        self.maintenance=self._service.maintenance
        return result

    def call_blocking(self,name,*args,**kwargs):
        """Explicit compatibility API for scripts/tests, never used by application UI."""
        return self._executor.submit(self._invoke,name,args,kwargs).result()

    def submit(self,name,args,callback,failed,kwargs=None):
        request=str(uuid4());self._callbacks[request]=(callback,failed)
        future=self._executor.submit(self._invoke,name,args,kwargs or {})
        future.add_done_callback(lambda f:self._finished(request,f))
        return request

    def _finished(self,request,future):
        try:value,error=future.result(),None
        except Exception as exc:value,error=None,str(exc)
        if request=='open' and error:
            self._executor_stopped=True;self._executor.shutdown(wait=False)
        if self._service is not None:self.maintenance=self._service.maintenance
        if not self._closed:self.completed.emit(request,value,error)

    def _deliver(self,request,value,error):
        callbacks=self._callbacks.pop(request,None)
        if callbacks:callbacks[1 if error else 0](error if error else value)

    def close(self):
        if self._closed:return
        self._closed=True;self._callbacks.clear()
        if self._executor_stopped:return
        def shutdown():
            if self._service is not None and not self._service.maintenance:self._service.close()
        self._executor.submit(shutdown).result();self._executor.shutdown(wait=True)


# Finite compatibility surface for diagnostic scripts and fixtures.
# UI queries use read_model or submit; there is no universal __getattr__ proxy.
def _blocking_method(name):
    def method(self,*args,**kwargs):return self.call_blocking(name,*args,**kwargs)
    return method

for _name in set(PersonnelGateway._WRITES)|set(('settings','set_setting','create_plan','add_passenger','bind_record','resolve_location',
              'passenger','passengers','crew_records','context','assert_context','save_berth','berth_versions',
              'berth_summaries','berth_version','latest_berth','update_settings','rename_plan','history',
              'planning_source','port_name','_validate_route','text_case_preview','import_preview')):
    setattr(PersonnelGateway,_name,_blocking_method(_name))
