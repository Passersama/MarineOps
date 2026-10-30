"""Independent replay of a complete transport contract; never uses solver transitions."""
from __future__ import annotations

from .personnel_import import PersonnelError, digest


def validate_route(problem, stops, assignments):
    errors = list(problem.get('errors', []));keys = set();order = {}
    for i, stop in enumerate(stops):
        if stop['id'] in order:errors.append('Repeated visit identity')
        order[stop['id']] = i
    tasks = {t['key']: t for t in problem['tasks']}
    for key, task in tasks.items():
        assignment = assignments.get(key)
        if not isinstance(assignment, dict):
            errors.append(f'{key}: missing pickup / delivery assignment');continue
        pick, drop = assignment.get('pick'), assignment.get('drop')
        if drop not in order:
            errors.append(f'{key}: destination delivery is missing');continue
        if stops[order[drop]]['vessel_id'] != task['to_id']:
            errors.append(f'{key}: delivery at the wrong location')
        if task['initial']:
            if pick is not None:errors.append(f'{key}: initially loaded task has an extra pickup')
        elif pick not in order:
            errors.append(f'{key}: source pickup is missing')
        elif stops[order[pick]]['vessel_id'] != task['from_id'] or order[pick] >= order[drop]:
            errors.append(f'{key}: pickup location or pickup-before-delivery order is invalid')
        if task['previous']:
            previous = assignments.get(task['previous'], {})
            prior_drop = previous.get('drop')
            if pick not in order or prior_drop not in order or order[pick] <= order[prior_drop]:
                errors.append(f'{key}: next leg must pick up on a later actual call')
        for side, visit in problem.get('locked', {}).get(key, {}).items():
            if assignment.get(side) != visit:errors.append(f'{key}: locked {side} changed')
        keys.add(key)
    positions = []
    for pin in problem.get('pins', []):
        if pin['id'] not in order or stops[order[pin['id']]]['vessel_id'] != pin['location_id']:
            errors.append('A retained visit is missing or changed')
        else:positions.append(order[pin['id']])
    if positions != sorted(positions):errors.append('Retained visit order changed')
    if set(assignments) - set(tasks):errors.append('Assignments contain tasks outside the required scope')
    cost = [sum(s['vessel_id'] != problem['shore_id'] for s in stops),
            sum(s['vessel_id'] == problem['shore_id'] for s in stops)]
    return {'valid': not errors, 'errors': list(dict.fromkeys(errors)), 'required': len(tasks), 'cost': cost}


def validate_contract(problem):
    """Drafts may have route issues, but their persisted contract must remain readable."""
    if (not isinstance(problem, dict) or problem.get('version') not in {1, 2} or
        not isinstance(problem.get('tasks'), list) or not isinstance(problem.get('pins'), list) or
        not isinstance(problem.get('locked'), dict) or not isinstance(problem.get('errors'), list) or
        not all(isinstance(e,str) for e in problem['errors'])):
        raise PersonnelError('Unsupported automatic transport contract.')
    task_keys=set()
    for t in problem['tasks']:
        if (not isinstance(t,dict) or not {'key','from_id','to_id','initial','previous','person_id','leg_index'}<=t.keys() or
            not isinstance(t['key'],str) or not t['key'].startswith(('Passengers:','Materials:')) or
            type(t['initial']) is not bool or type(t['to_id']) is not int or
            (t['from_id'] is not None and type(t['from_id']) is not int) or
            (t['previous'] is not None and not isinstance(t['previous'],str)) or
            type(t['leg_index']) is not int or t['leg_index']<1 or not isinstance(t['person_id'],str) or t['key'] in task_keys):
            raise PersonnelError('Invalid task in automatic transport contract.')
        task_keys.add(t['key'])
    for pin in problem['pins']:
        if (not isinstance(pin,dict) or not {'id','location_id'}<=pin.keys() or
            type(pin['id']) not in (str,int) or type(pin['location_id']) is not int):
            raise PersonnelError('Invalid retained visit in automatic transport contract.')
    for key,assignment in problem['locked'].items():
        if key not in task_keys or not isinstance(assignment,dict) or set(assignment)-{'pick','drop'}:
            raise PersonnelError('Invalid locked assignment in automatic transport contract.')
    unsigned = {k: v for k, v in problem.items() if k != 'hash'}
    if digest(unsigned) != problem.get('hash'):
        raise PersonnelError('The automatic transport contract changed. Replan the route.')


def validate_saved_plan(plan):
    """Validate route AND all four output groups before publishing or exporting."""
    from .plan_validation import validate_output_groups
    validate_output_groups(plan)
    problem = plan.get('transport_contract')
    if problem is None:return
    validate_contract(problem)
    assignments = plan.get('assignments', {})
    stops = [{'id': s['id'], 'vessel_id': s['vessel_id']} for s in plan['stops']]
    check = validate_route(problem, stops, assignments)
    tasks = {t['key'] for t in problem['tasks']}
    task_specs = {t['key']: t for t in problem['tasks']}
    if len(tasks)!=len(problem['tasks']):
        check['errors'].append('Duplicate tasks in automatic transport contract.')
    if set(plan.get('included', [])) != tasks:
        check['errors'].append('The plan omits required transport tasks.')
    for side, groups in (('pick', ('pick_passengers', 'pick_materials')),
                         ('drop', ('drop_passengers', 'drop_materials'))):
        actual = {}
        for stop in plan['stops']:
            for group in groups:
                for row in stop[group]:
                    key = row.get('task_key') or row['kind'] + ':' + str(row['id'])
                    spec=task_specs.get(key)
                    if spec and (row.get('from_id')!=spec['from_id'] or row.get('to_id')!=spec['to_id']):
                        check['errors'].append(f'{key}: output task source or destination changed.')
                    actual.setdefault(key, []).append(stop['id'])
        expected = {k: [a[side]] for k, a in assignments.items() if a.get(side) is not None}
        if actual != expected:check['errors'].append(f'{side} groups disagree with task assignments.')
    if check['errors']:
        raise PersonnelError('Incomplete automatic plan: ' + '; '.join(check['errors']))
