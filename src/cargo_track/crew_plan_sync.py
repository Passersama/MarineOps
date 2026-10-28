"""Refresh current crew plans while retaining the saved audit snapshots."""
import copy
from uuid import uuid4

from .berth_plan import generate_plan, plan_assignments, leg_choices, task_key
from .personnel_routes import leg_order, transfer_origin
from .personnel_import import digest


def complete_crew_route(snapshot, people, *, departure=False):
    """Add missing calls without moving any existing visit or comment."""
    route = copy.deepcopy(snapshot['stops'])
    shore = next((r['id'] for r in snapshot['locations'] if r['kind'] == 'SHORE'), None)
    locations = {r['id']: r for r in snapshot['locations'] if r['active']}
    def insert(location, position):
        route.insert(position, {'id': 'plan:' + str(uuid4()), 'vessel_id': location,
                                'vessel_name_snapshot': locations[location]['name']})
    if departure and shore in locations and not any(s['vessel_id'] == shore for s in route) and any(
            p.get('from_id') == shore and not p.get('previous_task_id') for p in people):
        insert(shore, 0)
    if shore in locations and not any(s['vessel_id'] == shore for s in route[1:]) and any(
            p.get('to_id') == shore for p in people):
        insert(shore, len(route))
    for person in sorted(people, key=leg_order):
        for side in ('from', 'to'):
            location = person.get(side + '_id')
            if location not in locations or location == shore or (side == 'from' and transfer_origin(person, snapshot)):
                continue
            if any(s['vessel_id'] == location for s in route):
                continue
            ports = [i for i, s in enumerate(route) if s['vessel_id'] == shore]
            position = len(route)
            if side == 'from' and ports:
                position = next((i for i in ports if i > 0), len(route))
            elif side == 'to' and ports:
                position = ports[0] + 1
            insert(location, position)
    return route


def refresh_crew_plan(plan, snapshot, people, context):
    source = copy.deepcopy(snapshot)
    source['require_personnel_port_calls'] = True
    source['stops'] = [{'id': s['id'], 'vessel_id': s['vessel_id'],
                        'vessel_name_snapshot': s['name']} for s in plan['stops']]
    old_assignments = plan_assignments(plan)
    selections = copy.deepcopy(plan.get('task_selections', {}))
    # Automatically unavailable entries are retried when their source changes.
    selections = {k: v for k, v in selections.items() if v.get('state') == 'user_excluded' or k.startswith('Materials:')}
    edits, bases = {}, {}
    people = copy.deepcopy(people)
    for person in people:
        key = task_key(person)
        for field, value in plan.get('draft_edits', {}).get(key, {}).items():
            if field in ('name', 'position') and person.get(field, '') == plan.get('override_bases', {}).get(key, {}).get(field):
                edits.setdefault(key, {})[field] = value
                bases.setdefault(key, {})[field] = person.get(field, '')
                person[field] = value
    selected = {task_key(p) for p in people if selections.get(task_key(p), {}).get('state') != 'user_excluded'}
    source['stops'] = complete_crew_route(source, [p for p in people if task_key(p) in selected], departure=True)
    resolved = {}
    for person in sorted(people, key=leg_order):
        identifier = task_key(person)
        if identifier not in selected:
            continue
        choices = leg_choices(source, person, resolved, selected)
        previous = old_assignments.get(identifier)
        if previous in choices:
            resolved[identifier] = previous
        elif choices:
            resolved[identifier] = choices[0]
    materials = plan.get('source_dependencies', {}).get('cargo_ids')
    if materials is None:
        materials = sorted({int(k.split(':', 1)[1]) for k in plan.get('selected_tasks', plan.get('included', []))
                            if k.startswith('Materials:')})
    assignments = {k: v for k, v in old_assignments.items() if k.startswith('Materials:')}
    assignments.update(resolved)
    result = generate_plan(source, people, materials, plan['date'], plan['port_name'], mode='Final',
                           assignments=assignments, selections=selections, personnel_plan_id=plan['personnel_plan_id'])
    comments = {s['id']: s.get('comment', '') for s in plan['stops']}
    for stop in result['stops']:
        stop['comment'] = comments.get(stop['id'], '')
        stop['optimizer_keep'] = next((s.get('optimizer_keep', False) for s in plan['stops'] if s['id'] == stop['id']), False)
    result.update(personnel_context=context, personnel_source_path=context['path'],
                  family_id=plan['family_id'], base_version_id=plan['id'], revision_reviewed=True,
                  available_tasks=[task_key(p) for p in people] + ['Materials:' + str(n) for n in materials],
                  draft_edits=edits, override_bases=bases, automatic_crew_sync=True)
    if plan.get('optimization'):
        result['optimization'] = {**plan['optimization'], 'status': 'STALE'}
    result['plan_route_hash'] = digest(result['stops'])
    return result
