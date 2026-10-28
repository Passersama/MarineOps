"""Dashboard integration tests against actual isolated Cargo/Personnel services."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from cargo_track.berth_plan import generate_plan
from cargo_track.dashboard_data import crew_at_visit, personnel_progress, read_dashboard
from cargo_track.domain import Command
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_service import PersonnelService
from cargo_track.service import ApplicationService
from cargo_track.worker import DatabaseWorker


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cargo=ApplicationService(self.root/'cargo-track.sqlite3');self.cargo.open()
        self.vessels={name:self.command('create_vessel',{'name':name})['id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','Niger')}
        self.command('create_voyage',{'name':'Dashboard voyage'})
        self.visits=[self.command('add_stop',{'vessel_id':self.vessels[name]})['stop_id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','BGP Innovator')]
        self.command('set_setting',{'key':'transfer_vessel_name','value':'Niger'})
        for description,source,target in [('Hard Disk','BGP Innovator','BGP Victor'),('GPS cable','BGP Innovator','DFKT2'),('Spare parts','BGP Victor','BGP Innovator'),('Done item','HB6','DFKT2'),('Deleted item','HB6','BGP Victor')]:
            self.command('create_transfer',{'description':description,'from_location_id':self.vessels[source],'to_location_id':self.vessels[target]})
        self.command('pick_up',{'no':3,'expected_version':0,'confirmed_location':True})
        self.command('pick_up',{'no':4,'expected_version':0,'confirmed_location':True})
        self.command('deliver',{'no':4,'expected_version':1,'confirmed_location':True})
        self.command('void_transfer',{'no':5,'expected_version':0,'reason':'Test deletion'})
        self.command('choose_stop',{'stop_id':self.visits[2]})
        self.personnel=PersonnelService(self.root/'personnel-transfer.sqlite3')
        self.personnel.set_setting('transfer_vessel_name','Niger')
        self.list_id=self.personnel.create_plan('October roster','2026-10-12')
        self.ids=[]
        for name,position,source,target in [('Same Name','Engineer','Niger','BGP Innovator'),('Same Name','Able Seaman','Niger','BGP Innovator'),('Omar Hassan','Electrician','Niger','BGP Innovator'),('Daniel Mensah','Chief Officer','BGP Innovator','DFKT2'),('Ravi Menon','Able Seaman','BGP Innovator','DFKT2')]:
            record=self.personnel.bind_record({'name':name,'position':position,'direction':'Transfer','date':'2026-10-12','from_name':source,'to_name':target},read_cargo(self.cargo.path))
            self.ids.append(self.personnel.add_passenger(self.list_id,record))
        self.saved=self.save_plan()
    def command(self,name,payload):return self.cargo.handle(Command(str(uuid4()),name,payload)).result
    def save_plan(self,published=True):
        source=self.personnel.planning_source(read_cargo(self.cargo.path,active_only=True))
        people=self.personnel.crew_records(self.list_id,source)
        plan=generate_plan(source,people,[],'2026-10-12',self.personnel.port_name(source),mode='Final',personnel_plan_id=self.list_id)
        self.assertFalse(plan['issues'],plan['issues'])
        plan['personnel_context']=self.personnel.context(self.list_id)
        plan['personnel_source_path']=str(self.personnel.path)
        return self.personnel.save_berth(plan,published)
    def read(self,selected=None):return read_dashboard(self.cargo.path,self.personnel.path,selected)
    def tearDown(self):
        self.personnel.close();self.cargo.close();self.temp.cleanup()
    def test_counts_and_directions_use_actual_non_deleted_data(self):
        result=self.read();c=result['cargo'];p=result['personnel']
        self.assertEqual(c['counts'],{'Waiting':2,'On Board':1,'Done':1});self.assertEqual(c['total'],4)
        self.assertEqual((c['pickups'],c['deliveries']),(2,1))
        self.assertEqual([r['no'] for r in c['cargo_rows']],[1,2,3])
        self.assertEqual((p['boarding'],p['leaving']),(3,2));self.assertEqual(p['status'],'ready')
        self.assertEqual(sum(r['name']=='Same Name' for r in p['rows']),2)
        self.assertEqual(next(r['movement'] for r in p['rows'] if r['name']=='Daniel Mensah'),'Leaving')
    def test_reader_changes_neither_database_nor_revision(self):
        before=[path.read_bytes() for path in (self.cargo.path,self.personnel.path)]
        revision=self.cargo.workspace_snapshot()['revision']
        for _ in range(3):self.read()
        self.assertEqual(before,[path.read_bytes() for path in (self.cargo.path,self.personnel.path)])
        self.assertEqual(revision,self.cargo.workspace_snapshot()['revision'])
    def test_repeated_vessel_uses_exact_visit_not_name(self):
        self.command('choose_stop',{'stop_id':self.visits[4]})
        p=self.read()['personnel'];self.assertEqual(p['status'],'ready')
        self.assertEqual((p['boarding'],p['leaving']),(0,0))
    def test_no_current_visit_does_not_show_old_names(self):
        self.command('clear_current_stop',{'expected_stop_id':self.visits[2]})
        p=self.read()['personnel'];self.assertIsNone(p['boarding']);self.assertEqual(p['rows'],[])
    def test_changed_roster_refreshes_latest_counts_and_retains_history(self):
        record=self.personnel.passenger(self.ids[0]);record['position']='Changed role'
        self.personnel.edit_crew_entry(self.ids[0],record,record['version'])
        p=self.read()['personnel'];self.assertEqual(p['status'],'ready')
        self.assertEqual((p['boarding'],p['leaving']),(3,2))
        self.assertEqual('Changed Role',next(r['position'] for r in p['rows'] if r['task_id']==self.ids[0]))
        self.assertNotEqual(self.saved['id'],p['selected_id'])
        self.assertIn(self.saved,self.personnel.berth_versions())
        self.assertEqual(self.read(self.saved['id'])['personnel']['status'],'stale')
    def test_destination_edit_moves_dashboard_boarding_to_new_ship(self):
        record=self.personnel.passenger(self.ids[0])
        edited=self.personnel.bind_record({**record,'to_name':'DFKT2'},read_cargo(self.cargo.path))
        self.personnel.edit_crew_entry(record['id'],edited,record['version'])
        p=self.read()['personnel'];self.assertEqual(p['status'],'ready')
        self.assertEqual((p['boarding'],p['leaving']),(2,2))
        self.command('choose_stop',{'stop_id':self.visits[3]})
        p=self.read()['personnel'];self.assertEqual(p['status'],'ready')
        self.assertEqual(p['boarding'],3)
        self.assertIn(record['id'],[r['task_id'] for r in p['rows']])
    def test_legacy_stale_roster_can_refresh_read_only_in_automatic_mode(self):
        record=self.personnel.passenger(self.ids[0])
        with patch.object(self.personnel,'_sync_crew_plans'):
            self.personnel.edit_crew_entry(record['id'],{**record,'position':'Current role'},record['version'])
        before=[path.read_bytes() for path in (self.cargo.path,self.personnel.path)]
        p=self.read()['personnel'];self.assertEqual(p['status'],'ready')
        self.assertEqual('Current Role',next(r['position'] for r in p['rows'] if r['task_id']==record['id']))
        self.assertEqual(before,[path.read_bytes() for path in (self.cargo.path,self.personnel.path)])
    def test_roster_change_during_cargo_validation_is_rejected(self):
        original=read_cargo
        def changed(*args,**kwargs):
            value=original(*args,**kwargs);record=self.personnel.passenger(self.ids[0]);record['position']='During read'
            self.personnel.edit_crew_entry(self.ids[0],record,record['version']);return value
        with patch('cargo_track.dashboard_data.read_cargo',side_effect=changed):p=self.read()['personnel']
        self.assertEqual(p['status'],'stale');self.assertEqual(p['rows'],[])
    def test_removed_history_is_not_offered(self):
        self.personnel.clear_berth_history([self.saved['id']]);p=self.read()['personnel']
        self.assertEqual(p['choices'],[]);self.assertEqual(p['rows'],[])
    def test_saved_draft_is_labeled_and_selectable(self):
        draft=self.save_plan(False);p=self.read(draft['id'])['personnel']
        self.assertEqual(p['selected_id'],draft['id']);self.assertIn('Draft',p['plan_label'])
    def test_missing_personnel_database_is_not_created(self):
        missing=self.root/'not-created'/'personnel-transfer.sqlite3'
        p=read_dashboard(self.cargo.path,missing)['personnel'];self.assertEqual(p['status'],'empty');self.assertFalse(missing.exists())
    def test_another_voyage_does_not_reuse_personnel_plan(self):
        self.command('create_voyage',{'name':'Different voyage'});p=self.read()['personnel']
        self.assertEqual(p['choices'],[]);self.assertEqual(p['rows'],[])
    def test_cargo_statistics_include_new_records_outside_route(self):
        self.command('create_transfer',{'description':'Outside route','from_location_id':self.vessels['Niger'],'to_location_id':self.vessels['HB6']})
        result=self.read();self.assertEqual(result['cargo']['total'],5);self.assertEqual(result['personnel']['status'],'ready')
    def test_voyage_summary_carries_backlog_but_excludes_old_completed(self):
        with patch('cargo_track.service.now_utc',return_value='2099-01-01T00:00:00.000000Z'):
            self.command('create_voyage',{'name':'New voyage'})
            self.command('create_transfer',{'description':'New trip cargo','from_location_id':self.vessels['Niger'],'to_location_id':self.vessels['HB6']})
            self.command('deliver',{'no':3,'expected_version':1,'confirmed_location':True})
            # Reopening a transfer completed before departure does not put it in
            # the original departure backlog.
            self.command('correct_transfer',{'no':4,'expected_version':2,'status':'Waiting','reason':'Reopened historical task'})
        counts=self.read()['cargo']['counts']
        self.assertEqual(counts,{'Waiting':3,'On Board':0,'Done':1})
        self.assertEqual(self.cargo.workspace_snapshot()['counts']['open'],4)
    def test_no_voyage_has_zero_voyage_cargo_counts(self):
        self.command('delete_voyage',{'voyage_id':self.cargo.workspace_snapshot()['current_voyage_id']})
        self.assertEqual(self.read()['cargo']['counts'],{'Waiting':0,'On Board':0,'Done':0})
    def test_same_second_voyage_creation_does_not_include_prior_done(self):
        with patch('cargo_track.service.now_utc',return_value='2099-01-01T00:00:00+00:00'):
            self.command('deliver',{'no':3,'expected_version':1,'confirmed_location':True})
            self.command('create_voyage',{'name':'Same second voyage'})
            self.command('create_transfer',{'description':'Created in same second','from_location_id':self.vessels['Niger'],'to_location_id':self.vessels['HB6']})
        self.assertEqual(self.read()['cargo']['counts'],{'Waiting':3,'On Board':0,'Done':0})
    def test_personnel_progress_completes_only_deliveries_before_current_visit(self):
        self.assertEqual(self.read()['personnel']['progress'],{'Completed':0,'Pending':5})
        self.command('choose_stop',{'stop_id':self.visits[3]})
        self.assertEqual(self.read()['personnel']['progress'],{'Completed':3,'Pending':2})
        self.command('choose_stop',{'stop_id':self.visits[4]})
        self.assertEqual(self.read()['personnel']['progress'],{'Completed':5,'Pending':0})
        self.command('choose_stop',{'stop_id':self.visits[2]})
        self.assertEqual(self.read()['personnel']['progress'],{'Completed':0,'Pending':5})
    def test_personnel_progress_counts_linked_legs_once_each_not_people_or_actions(self):
        first={'id':'leg1','person_id':'same','task_key':'Passengers:leg1'}
        second={'id':'leg2','person_id':'same','task_key':'Passengers:leg2'}
        pending={'id':'pending','person_id':'other'}
        plan={'stops':[{'id':'a','pick_passengers':[first]},
                       {'id':'b','drop_passengers':[first,copy.deepcopy(first)]},
                       {'id':'c','pick_passengers':[second,pending]},
                       {'id':'d','drop_passengers':[second]}],
              'selected_tasks':['Passengers:leg1','Passengers:leg2','Passengers:pending','Passengers:unresolved','Materials:10']}
        self.assertEqual(personnel_progress(plan,'c'),{'Completed':1,'Pending':3})
        self.assertEqual(personnel_progress(plan,'d'),{'Completed':1,'Pending':3})
        self.assertIsNone(personnel_progress(plan,None))
    def test_invalid_personnel_scope_clears_progress(self):
        self.command('clear_current_stop',{'expected_stop_id':self.visits[2]})
        self.assertIsNone(self.read()['personnel'].get('progress'))
        record=self.personnel.passenger(self.ids[0]);record['position']='Changed'
        self.personnel.edit_crew_entry(record['id'],record,record['version'])
        self.assertIsNone(self.read()['personnel'].get('progress'))
    def test_duplicate_task_for_same_person_is_counted_once(self):
        plan=copy.deepcopy(self.saved);stop=next(s for s in plan['stops'] if s['id']==self.visits[2])
        stop['drop_passengers'].append(copy.deepcopy(stop['drop_passengers'][0]))
        rows=crew_at_visit(plan,self.visits[2]);self.assertEqual(sum(r['movement']=='Boarding' for r in rows),3)
    def independent_plan(self, repeated=False):
        source=self.personnel.planning_source(read_cargo(self.cargo.path))
        for i,stop in enumerate(source['stops']):stop['id']='plan:independent-'+str(i)
        if not repeated:source['stops']=source['stops'][:4]
        plan=generate_plan(source,self.personnel.crew_records(self.list_id,source),[],'2026-10-12',self.personnel.port_name(source),mode='Final',personnel_plan_id=self.list_id)
        # Keep the real Cargo route as the reference dependency for the independent plan.
        real=read_cargo(self.cargo.path);source['reference_stops']=real['stops']
        from cargo_track.personnel_cargo import dependency_hash
        plan['dependency_hash']=dependency_hash(source,plan['source_dependencies'])
        plan['personnel_context']=self.personnel.context(self.list_id)
        return self.personnel.save_berth(plan,True)
    def test_independent_unique_plan_visit_shows_boarding_and_leaving(self):
        plan=self.independent_plan();p=self.read(plan['id'])['personnel']
        self.assertEqual(p['status'],'ready');self.assertEqual((p['boarding'],p['leaving']),(3,2))
        self.assertEqual(p['visit_id'],'plan:independent-2')
    def test_independent_repeated_plan_visit_requires_explicit_choice(self):
        plan=self.independent_plan(True);p=self.read(plan['id'])['personnel']
        self.assertEqual(p['status'],'choose_visit');self.assertIsNone(p['boarding']);self.assertEqual(p['rows'],[])
        self.assertEqual(len(p['visit_choices']),2)
        selected=read_dashboard(self.cargo.path,self.personnel.path,plan['id'],selected_visit='plan:independent-2')['personnel']
        self.assertEqual((selected['boarding'],selected['leaving']),(3,2))
        last=read_dashboard(self.cargo.path,self.personnel.path,plan['id'],selected_visit='plan:independent-4')['personnel']
        self.assertEqual((last['boarding'],last['leaving']),(0,0))
    def test_health_query_reports_real_foreign_key_failure(self):
        self.assertEqual(self.cargo.health_report()['foreign_keys'],'ok')
        self.cargo.db.execute('PRAGMA foreign_keys=OFF')
        self.cargo.db.execute('UPDATE voyage_stops SET vessel_id=999999 WHERE id=?',(self.visits[0],))
        worker=DatabaseWorker(self.cargo.path);worker.service=self.cargo;responses=[]
        worker.result.connect(lambda request,envelope:responses.append(envelope))
        worker.request('health-test','_health',{})
        self.assertEqual(responses[0]['data']['foreign_keys'],'failed')
        self.assertTrue(responses[0]['data']['foreign_key_details'])


if __name__=='__main__':unittest.main()
