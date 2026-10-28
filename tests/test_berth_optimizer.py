"""Independent small-route enumeration and live service contract regressions."""
import copy
from itertools import product
from pathlib import Path
import random
import tempfile
import unittest
from uuid import uuid4

from cargo_track.berth_optimizer import make_problem, solve, materialize
from cargo_track.berth_optimization_validation import validate_route, validate_saved_plan
from cargo_track.berth_plan import cargo_tasks, generate_plan, export_plan
from cargo_track.domain import Command
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_import import PersonnelError
from cargo_track.personnel_service import PersonnelService
from cargo_track.service import ApplicationService


def snapshot():
    return {'locations':[{'id':i,'name':str(i),'kind':'SHORE' if i==0 else 'VESSEL','active':True} for i in range(4)],
            'settings':{},'plan_transfer_vessel':'Boat'}


def passenger(i, source, target, previous=None):
    return {'id':str(i),'kind':'Passengers','name':'Test '+str(i),'position':'Engineer','from_id':source,'to_id':target,
            'from_name':str(source),'to_name':str(target),'person_id':'chain' if previous else str(i),
            'leg_index':2 if previous else 1,'previous_task_id':str(previous) if previous else None,'issues':[]}


def oracle(tasks, max_calls=6):
    """Enumerate complete vessel sequences, independently simulating task phases."""
    locations=sorted({r['from_id'] for r in tasks}|{r['to_id'] for r in tasks})
    for length in range(max_calls+1):
        for route in product(locations,repeat=length):
            phase={t['key']:1 if t['initial'] else 0 for t in tasks}
            for location in route:
                before=phase.copy()
                for task in tasks:
                    key=task['key']
                    if before[key]==1 and task['to_id']==location:phase[key]=2
                    if before[key]==0 and task['from_id']==location and (not task['previous'] or before[task['previous']]==2):phase[key]=1
            if all(v==2 for v in phase.values()):return length
    return None


class OptimizerTests(unittest.TestCase):
    def solution(self,rows,**kwargs):
        problem=make_problem(snapshot(),rows,[],**kwargs);result=solve(problem)
        self.assertEqual(result['status'],'OPTIMAL',result)
        stops,assignments=materialize(result,snapshot())
        check=validate_route(problem,stops,assignments);self.assertTrue(check['valid'],check)
        self.assertEqual(check['cost'],result['cost'])
        return problem,result,stops,assignments
    def test_shared_source_needs_three_calls(self):
        self.assertEqual(self.solution([passenger(1,1,2),passenger(2,1,3)])[1]['cost'],[3,0])
    def test_round_trip_counts_same_vessel_twice(self):
        self.assertEqual(self.solution([passenger(1,1,2),passenger(2,2,1)])[1]['cost'],[3,0])
    def test_three_ship_cycle_needs_four_calls(self):
        self.assertEqual(self.solution([passenger(1,1,2),passenger(2,2,3),passenger(3,3,1)])[1]['cost'],[4,0])
    def test_linked_person_reboards_on_a_second_actual_call(self):
        first=passenger(1,1,2);first['person_id']='chain'
        problem,result,stops,assignments=self.solution([first,passenger(2,2,3,1)])
        self.assertEqual(result['cost'],[4,0])
        order={s['id']:i for i,s in enumerate(stops)}
        self.assertGreater(order[assignments['Passengers:2']['pick']],order[assignments['Passengers:1']['drop']])
        self.assertEqual(sum(s['vessel_id']==2 for s in stops),2)
    def test_port_later_leg_requires_actual_return_and_pickup(self):
        first=passenger(1,1,0);first['person_id']='chain'
        _,result,_,assignments=self.solution([first,passenger(2,0,2,1)])
        self.assertEqual(result['cost'],[2,2]);self.assertIsNotNone(assignments['Passengers:2']['pick'])
    def test_onboard_material_does_not_call_original_source(self):
        material={**passenger(1,1,2),'kind':'Materials','status':'On Board'}
        problem=make_problem(snapshot(),[],[material]);result=solve(problem)
        self.assertEqual(result['cost'],[1,0]);self.assertEqual(result['assignments']['Materials:1']['pick'],None)
    def test_port_origin_has_actual_port_pickup_before_departure(self):
        _,result,stops,assignments=self.solution([passenger(1,0,2)])
        self.assertEqual(result['cost'],[1,1])
        self.assertEqual(stops[0]['id'],assignments['Passengers:1']['pick'])
        self.assertEqual(stops[0]['vessel_id'],0)
    def test_sign_off_then_port_then_sign_on_uses_one_port_between_ship_calls(self):
        _,result,stops,assignments=self.solution([passenger(1,1,0),passenger(2,0,2)])
        self.assertEqual(result['cost'],[2,1])
        self.assertEqual([1,0,2],[s['vessel_id'] for s in stops])
        self.assertEqual(assignments['Passengers:1']['drop'],assignments['Passengers:2']['pick'])
    def test_retained_same_vessel_visits_count_separately(self):
        _,result,stops,_=self.solution([],pins=[{'id':'a','vessel_id':1},{'id':'b','vessel_id':1}])
        self.assertEqual(result['cost'],[2,0]);self.assertEqual([s['id'] for s in stops],['a','b'])
    def test_locked_assignments_are_respected(self):
        _,result,_,assignments=self.solution([passenger(1,1,2)],pins=[{'id':'pick','vessel_id':1},{'id':'drop','vessel_id':2}],
                                             locked={'Passengers:1':{'pick':'pick','drop':'drop'}})
        self.assertEqual(result['cost'],[2,0]);self.assertEqual(assignments['Passengers:1'],{'pick':'pick','drop':'drop'})
    def test_conflicting_locked_order_is_proven_infeasible(self):
        problem=make_problem(snapshot(),[passenger(1,1,2)],[],pins=[{'id':'drop','vessel_id':2},{'id':'pick','vessel_id':1}],
                             locked={'Passengers:1':{'pick':'pick','drop':'drop'}})
        self.assertEqual(solve(problem)['status'],'INFEASIBLE_PROVEN')
    def test_excluded_preceding_leg_is_not_silently_cut(self):
        first=passenger(1,1,2);first['person_id']='chain'
        problem=make_problem(snapshot(),[first,passenger(2,2,3,1)],[],excluded=['Passengers:1'])
        self.assertEqual(solve(problem)['status'],'INPUT_INVALID')
    def test_limit_and_cancellation_do_not_claim_no_solution_or_minimum(self):
        problem=make_problem(snapshot(),[passenger(1,1,2)],[])
        self.assertEqual(solve(problem,max_states=1)['status'],'NO_SOLUTION_YET')
        self.assertEqual(solve(problem,cancelled=lambda:True)['status'],'CANCELLED')
        cycle=make_problem(snapshot(),[passenger(1,1,2),passenger(2,2,3),passenger(3,3,1)],[])
        candidate=solve(cycle,max_states=14)
        self.assertEqual(candidate['status'],'FEASIBLE')
        stops,assignments=materialize(candidate,snapshot())
        self.assertTrue(validate_route(cycle,stops,assignments)['valid'])
    def test_fixed_random_cases_agree_with_independent_enumeration(self):
        rng=random.Random(121)
        for case in range(24):
            rows=[passenger(i,*rng.sample([1,2,3],2)) for i in range(rng.randint(1,4))]
            problem,result,_,_=self.solution(rows)
            self.assertEqual(result['cost'][0],oracle(problem['tasks']),f'case {case}')
    def test_validator_rejects_missing_delivery_and_same_call_reboarding(self):
        first=passenger(1,1,2);first['person_id']='chain'
        problem,_,stops,assignments=self.solution([first,passenger(2,2,3,1)])
        wrong=copy.deepcopy(assignments);wrong['Passengers:2']['pick']=wrong['Passengers:1']['drop']
        self.assertFalse(validate_route(problem,stops,wrong)['valid'])
        wrong=copy.deepcopy(assignments);wrong['Passengers:2']['drop']=None
        self.assertFalse(validate_route(problem,stops,wrong)['valid'])
    def test_empty_scope_is_zero_calls_and_deterministic(self):
        problem,result,_,_=self.solution([]);self.assertEqual(result['cost'],[0,0])
        self.assertEqual(solve(problem)['visits'],result['visits'])
    def test_port_ties_agree_with_independent_sequence_enumeration(self):
        rng=random.Random(122)
        for _ in range(12):
            rows=[passenger(i,*rng.sample([0,1,2,3],2)) for i in range(2)]
            problem,result,_,_=self.solution(rows)
            best=None
            for length in range(5):
                for route in product([0,1,2,3],repeat=length):
                    phase={t['key']:1 if t['initial'] else 0 for t in problem['tasks']}
                    for location in route:
                        before=phase.copy()
                        for t in problem['tasks']:
                            if before[t['key']]==1 and t['to_id']==location:phase[t['key']]=2
                            if before[t['key']]==0 and t['from_id']==location:phase[t['key']]=1
                    if all(p==2 for p in phase.values()):
                        cost=(sum(x!=0 for x in route),route.count(0))
                        if best is None or cost<best:best=cost
            self.assertEqual(tuple(result['cost']),best)


class OptimizerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cargo=ApplicationService(self.root/'cargo.sqlite3');self.cargo.open()
        self.fleet=[self.command('create_vessel',{'name':n})['id'] for n in ('A','B','C')]
        self.command('create_voyage',{'name':'Optimizer trip'})
        for vessel in self.fleet:self.command('add_stop',{'vessel_id':vessel})
        self.service=PersonnelService(self.root/'personnel.sqlite3');self.roster=self.service.create_plan('Roster','2026-10-12')
        self.numbers=[]
        for a,b in ((0,1),(1,2),(2,0)):
            self.numbers.append(self.command('create_transfer',{'description':'Material','from_location_id':self.fleet[a],'to_location_id':self.fleet[b]})['no'])
    def tearDown(self):
        self.service.close();self.cargo.close();self.temp.cleanup()
    def command(self,name,args):return self.cargo.handle(Command(str(uuid4()),name,args)).result
    def plan(self):
        source=self.service.planning_source(read_cargo(self.cargo.path));source['reference_stops']=copy.deepcopy(source['stops'])
        people=self.service.crew_records(self.roster,source);materials=cargo_tasks(source,self.numbers)
        problem=make_problem(source,people,materials);result=solve(problem)
        stops,assignments=materialize(result,source,source['stops']);source['stops']=stops
        plan=generate_plan(source,people,self.numbers,'2026-10-12',self.service.port_name(source),mode='Final',
                           assignments=assignments,personnel_plan_id=self.roster,transport_contract=problem)
        plan['personnel_context']=self.service.context(self.roster);return plan
    def test_complete_materials_save_export_backup_restore(self):
        before=self.cargo.path.read_bytes();plan=self.plan();self.assertFalse(plan['issues'],plan['issues'])
        saved=self.service.save_berth(plan,True);validate_saved_plan(saved)
        export_plan(saved,self.root/'plan.xlsx');self.assertTrue((self.root/'plan.xlsx').is_file())
        backup=self.root/'backup.sqlite3';self.service.backup(backup);PersonnelService.validate_file(backup)
        self.service.restore(backup);self.assertEqual(len(self.service.berth_versions()),1)
        self.assertEqual(before,self.cargo.path.read_bytes())
    def test_incomplete_plan_cannot_bypass_service_by_clearing_issues(self):
        plan=self.plan();plan['stops']=plan['stops'][:-1];plan['issues']=[]
        with self.assertRaises(PersonnelError):self.service.save_berth(plan,True)
        with self.assertRaises(PersonnelError):export_plan(plan,self.root/'bad.xlsx')
    def test_new_unexcluded_person_requires_replanning(self):
        plan=self.plan();source=read_cargo(self.cargo.path)
        row=self.service.bind_record({'name':'New Person','position':'Engineer','from_name':'A','to_name':'B','date':'2026-10-12'},source)
        self.service.add_passenger(self.roster,row);plan['personnel_context']=self.service.context(self.roster)
        with self.assertRaises(PersonnelError):self.service.save_berth(plan,True)


if __name__=='__main__':unittest.main()
