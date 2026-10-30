"""Replay saved output groups without trusting the editor's issues list."""
from .personnel_import import PersonnelError, key
from .personnel_routes import leg_order, person_identity
from .plan_store import validate_plan_shape


def validate_output_groups(plan):
    validate_plan_shape(plan)
    if (not isinstance(plan.get('excluded',[]),list) or not isinstance(plan.get('assignments',{}),dict)
            or not isinstance(plan.get('task_selections',{}),dict)
            or any(not isinstance(v,dict) for v in plan.get('task_selections',{}).values())
            or not isinstance(plan.get('selected_tasks',[]),list)
            or any(not isinstance(t,str) for t in plan.get('selected_tasks',[]))):
        raise PersonnelError('Incomplete plan: invalid task selection or assignments.')
    errors = []
    order, tasks, movements = {}, {}, {}
    for index, stop in enumerate(plan['stops']):
        identifier = stop['id']
        if type(identifier) not in (str, int) or identifier in order:
            raise PersonnelError('Incomplete plan: repeated or invalid visit identity.')
        order[identifier] = index
        for group, kind, side in (('pick_passengers', 'Passengers', 'pick'),
                                  ('drop_passengers', 'Passengers', 'drop'),
                                  ('pick_materials', 'Materials', 'pick'),
                                  ('drop_materials', 'Materials', 'drop')):
            for row in stop[group]:
                if not isinstance(row, dict) or row.get('kind') != kind or not row.get('id'):
                    raise PersonnelError('Incomplete plan: invalid output task.')
                task = kind + ':' + str(row['id'])
                if row.get('task_key', task) != task:
                    errors.append(task + ': task identity disagrees with output group')
                previous = tasks.setdefault(task, row)
                for field in ('from_id', 'to_id', 'person_id', 'previous_task_id'):
                    before=person_identity(previous) if field=='person_id' else previous.get(field) or None
                    after=person_identity(row) if field=='person_id' else row.get(field) or None
                    if before != after:
                        # Reviewed Complete revisions retain the evidenced pickup
                        # text while a corrected destination applies to its future drop.
                        historical = (field == 'to_id' and plan['mode'] == 'Complete'
                                      and plan.get('pending_start_stop_id') in order
                                      and movements.get(task, {}).get('pick')
                                      and order[movements[task]['pick'][0]] < order[plan['pending_start_stop_id']])
                        if not historical:errors.append(task + ': pickup and delivery disagree on '+field)
                if side == 'drop':tasks[task] = row
                at = movements.setdefault(task, {'pick': [], 'drop': []})
                at[side].append(identifier)
                if stop['vessel_id'] != row.get('from_id' if side == 'pick' else 'to_id'):
                    errors.append(task + ': action at the wrong location')
    included = plan.get('included', [])
    if not isinstance(included, list) or any(not isinstance(t, str) for t in included):
        raise PersonnelError('Incomplete plan: invalid task scope.')
    if len(included) != len(set(included)) or set(included) != set(tasks):
        errors.append('Included tasks disagree with output groups')
    excluded = {r.get('task') for r in plan.get('excluded', []) if isinstance(r, dict)}
    explicit = {t for t, selection in plan.get('task_selections', {}).items()
                if selection.get('state') != 'included'}
    if set(tasks) & (excluded | explicit):
        errors.append('An excluded task still has output actions')
    legacy_revision=(plan['mode']=='Complete' and plan.get('pending_start_stop_id')
                     and 'output_contract_version' not in plan)
    if not plan.get('issues') and 'selected_tasks' in plan and not legacy_revision:
        if set(plan['selected_tasks']) - excluded != set(included):
            errors.append('Selected tasks are missing from the plan')
    shore = plan.get('shore_id')
    if shore is None:
        shore = next((s['vessel_id'] for s in plan['stops']
                      if s['id'] == 'PORT' or key(s['name']) == key(plan.get('port_name'))), None)
    if shore is None:
        shore = next((r.get(side + '_id') for r in tasks.values() for side in ('from', 'to')
                      if key(r.get(side + '_name')) == key(plan.get('port_name'))), None)
    visited = {s['vessel_id'] for s in plan['stops']}
    ports = shore is not None and shore in visited
    person_legs={}
    for task, row in tasks.items():
        pick, drop = movements[task]['pick'], movements[task]['drop']
        if len(pick) > 1 or len(drop) > 1:
            errors.append(task + ': repeated pickup or delivery')
            continue
        followup = (plan['mode'] != 'Final' and task in plan.get('followups', [])
                    and row.get('followup') and row.get('from_id') == shore and row.get('status') == 'Waiting')
        collection = (plan['mode'] == 'Final' and row['kind'] == 'Materials' and row.get('status') == 'Waiting'
                      and row.get('to_id') not in visited)
        if not drop and not (followup or collection):
            errors.append(task + ': destination delivery is missing')
        if (followup or collection) and not pick:
            errors.append(task + ': source pickup is missing')
        initial = (row.get('status') == 'On Board'
                   or (shore is not None and row.get('from_id') == shore)
                   or (row['kind'] == 'Passengers' and key(plan.get('transfer_vessel'))
                       and key(row.get('from_name')) == key(plan['transfer_vessel'])))
        if (plan['mode'] == 'Final' and row['kind'] == 'Passengers'
                and row.get('from_id') == shore
                and (plan.get('require_personnel_port_calls') or (ports and plan.get('output_contract_version')==1))):
            initial = False
        if not pick and not initial:
            errors.append(task + ': source pickup is missing')
        if pick and drop and order[pick[0]] >= order[drop[0]]:
            errors.append(task + ': pickup must precede delivery')
        requested = plan.get('assignments', {}).get(task)
        if requested and not plan.get('pending_start_stop_id'):
            actual = {'pick': pick[0] if pick else None, 'drop': drop[0] if drop else None}
            if requested != actual:
                errors.append(task + ': output actions disagree with the selected visits')
        previous_id = row.get('previous_task_id')
        if row['kind']=='Passengers':
            identity=(person_identity(row),leg_order(row))
            if identity in person_legs:errors.append(task+': duplicate personnel leg identity')
            person_legs[identity]=task
        if previous_id and plan['mode'] == 'Final':
            previous_key = 'Passengers:' + str(previous_id)
            previous = tasks.get(previous_key)
            earlier = movements.get(previous_key, {}).get('drop', [])
            if (not previous or person_identity(previous) != person_identity(row)
                    or leg_order(previous) + 1 != leg_order(row)
                    or previous.get('to_id') != row.get('from_id')
                    or not earlier or not pick or order[earlier[0]] >= order[pick[0]]):
                errors.append(task + ': next leg requires a later actual pickup after the preceding delivery')
    if errors:
        raise PersonnelError('Incomplete plan: ' + '; '.join(dict.fromkeys(errors)))
