import unittest
from cargo_track.berth_plan import route_options, generate_plan
from cargo_track.crew_plan_sync import complete_crew_route

class ExplicitPortTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'locations': [{'id': 1, 'kind': 'SHORE', 'name': 'Khafji Port', 'active': True}, {'id': 2, 'kind': 'VESSEL', 'name': 'A', 'active': True}], 'stops': [{'id': 10, 'vessel_id': 1, 'vessel_name_snapshot': 'Khafji Port'}, {'id': 11, 'vessel_id': 2, 'vessel_name_snapshot': 'A'}, {'id': 12, 'vessel_id': 1, 'vessel_name_snapshot': 'Khafji Port'}], 'current_stop_id': 10}
    def test_port_visits_are_distinct_and_in_order(self):
        task = {'kind': 'Materials', 'from_id': 1, 'to_id': 2, 'status': 'Waiting'}
        self.assertEqual([{'pick': 10, 'drop': 11}], route_options(self.snapshot, task))
        self.assertEqual([{'pick': 11, 'drop': 12}], route_options(self.snapshot, {**task, 'from_id': 2, 'to_id': 1}))
        self.assertEqual([], route_options({**self.snapshot, 'stops': self.snapshot['stops'][1:2]}, task))
    def test_crew_completion_does_not_insert_ports(self):
        source = {**self.snapshot, 'stops': self.snapshot['stops'][1:2]}
        self.assertEqual(source['stops'], complete_crew_route(source, [{'from_id': 1, 'to_id': 2}], departure=True))

class VoyagePortIntegrationTests(unittest.TestCase):
    def setUp(self):
        import test_personnel
        self.f = test_personnel.PersonnelTests()
        self.f.setUp()
    def tearDown(self):
        self.f.tearDown()
    def test_repeated_port_calls_support_cargo_and_personnel(self):
        from cargo_track.personnel_cargo import read_cargo
        from cargo_track.plan_validation import validate_output_groups
        f = self.f
        first = f.command('add_stop', {'vessel_id': f.shore})['stop_id']
        last = f.command('add_stop', {'vessel_id': f.shore})['stop_id']
        f.command('reorder_stops', {'stop_ids': [first, f.s1, last, f.s2, f.s3]})
        f.command('choose_stop', {'stop_id': first})
        number = f.command('create_transfer', {'description': 'Equipment', 'from_location_id': f.shore, 'to_location_id': f.a})['no']
        identifier = f.passenger(source='CHA', target='xxPort')
        plan = f.generate(cargo=[number])
        self.assertEqual([], plan['issues'])
        self.assertEqual([first, f.s1, last, f.s2, f.s3], [s['id'] for s in plan['stops']])
        self.assertEqual(number, int(plan['stops'][0]['pick_materials'][0]['id']))
        self.assertEqual(identifier, plan['stops'][2]['drop_passengers'][0]['id'])
        validate_output_groups(plan)
        f.command('pick_up', {'no': number, 'expected_version': f.cargo.repo.leg(number)['version']})
        self.assertEqual('On Board', f.cargo.repo.leg(number)['status'])
        self.assertEqual(first, read_cargo(f.cargo_path)['current_stop_id'])
    def test_optimizer_waiting_cargo_requires_port_visit(self):
        from cargo_track.berth_optimizer import make_problem, solve, materialize
        f=self.f
        source=f.snapshot
        task={'id':'1','kind':'Materials','name':'Box','from_id':f.shore,'to_id':f.a,'status':'Waiting','issues':[]}
        problem=make_problem(source, [], [task])
        result=solve(problem)
        stops, assignments=materialize(result, source)
        self.assertEqual('OPTIMAL',result['status'])
        self.assertEqual([f.shore, f.a], [s['vessel_id'] for s in stops])
        self.assertEqual(stops[0]['id'], assignments['Materials:1']['pick'])

    def test_port_rename_updates_live_views_and_preserves_saved_stop_name(self):
        from cargo_track.personnel_cargo import read_cargo
        from cargo_track.dashboard_data import read_cargo_summary
        f=self.f
        stop=f.command('add_stop', {'vessel_id': f.shore})['stop_id']
        before=read_cargo(f.cargo_path)
        saved=f.generate(personnel=[])
        old=next(s['name'] for s in saved['stops'] if s['id']==stop)
        f.command('set_setting', {'key':'port_name', 'value':'Khafji Port'})
        self.assertEqual('Khafji Port', next(s['vessel_name_snapshot'] for s in read_cargo(f.cargo_path)['stops'] if s['id']==stop))
        self.assertEqual('Khafji Port', next(s['vessel_name_snapshot'] for s in read_cargo_summary(f.cargo_path)['stops'] if s['id']==stop))
        self.assertEqual(old, next(s['name'] for s in saved['stops'] if s['id']==stop))
    def test_sign_on_and_sign_off_use_opposite_directions_at_intermediate_port(self):
        from cargo_track.personnel_cargo import read_cargo
        from cargo_track.berth_plan import generate_plan, plan_assignments
        f=self.f
        port=f.command('add_stop', {'vessel_id':f.shore})['stop_id']
        again=f.command('add_stop', {'vessel_id':f.a})['stop_id']
        f.command('reorder_stops', {'stop_ids':[f.s1, port, again, f.s2, f.s3]})
        for direction in ('Sign-off','Sign-on'):
            record=f.service.bind_record({'name':direction+' Crew','position':'Engineer','date':'2026-10-06',
                                          'direction':direction,'vessel':'CHA'},f.snapshot)
            f.service.add_passenger(f.plan,record)
        source=read_cargo(f.cargo_path)
        people=f.service.crew_records(f.plan,source)
        plan=generate_plan(source,people,[],'2026-10-06','xx port',mode='Final',personnel_plan_id=f.plan)
        self.assertEqual([],plan['issues'])
        assignments=plan_assignments(plan)
        off=next(p for p in people if p['direction']=='Sign-off')
        on=next(p for p in people if p['direction']=='Sign-on')
        self.assertEqual({'pick':f.s1,'drop':port},assignments['Passengers:'+off['id']])
        self.assertEqual({'pick':port,'drop':again},assignments['Passengers:'+on['id']])
        saved=f.service.save_berth(plan,True)
        self.assertEqual('Published',saved['status'])
        self.assertEqual([off['id']],[p['id'] for p in saved['stops'][1]['drop_passengers']])
        self.assertEqual([on['id']],[p['id'] for p in saved['stops'][1]['pick_passengers']])

    def test_sign_off_at_transfer_vessel_still_requires_vessel_pickup(self):
        from cargo_track.berth_optimizer import make_problem
        f=self.f
        source={**f.snapshot,'plan_transfer_vessel':'CHA'}
        person=f.service.bind_record({'name':'Returning','position':'Engineer','date':'2026-10-06',
                                      'direction':'Sign-off','vessel':'CHA'},source)
        person.update(id='signoff',kind='Passengers',status='Waiting')
        source['stops'].append({'id':'port','vessel_id':f.shore,'vessel_name_snapshot':'Port'})
        self.assertEqual([{'pick':f.s1,'drop':'port'}],route_options(source,person,'Final'))
        self.assertFalse(make_problem(source,[person],[])['tasks'][0]['initial'])
    def test_voyage_dialog_offers_port_even_when_fleet_is_empty(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cargo_track.ui import CargoTrackWindow
        calls=[]
        host=SimpleNamespace(snapshot={'locations':[{'id':1,'name':'Khafji Port','kind':'SHORE','active':True}]},
                             _submit=lambda *args:calls.append(args))
        with patch('cargo_track.ui.QInputDialog.getItem', return_value=('Khafji Port (Port)',True)) as picker:
            CargoTrackWindow.add_vessel_stop(host)
        self.assertEqual(['Khafji Port (Port)'],picker.call_args.args[3])
        self.assertEqual(('add_stop',{'vessel_id':1},'Added Khafji Port as a new stop.'),calls[0])
