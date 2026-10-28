"""Exact, cancellable call planning over immutable data; no Qt or database access."""
from __future__ import annotations

import copy
import heapq
import time
from itertools import count

from .personnel_import import digest
from .personnel_routes import transfer_origin, leg_order

RULES_VERSION = 2


def make_problem(snapshot, personnel, materials, *, excluded=(), pins=(), locked=None, reference_order=()):
    """Unavailability is not exclusion. Materials are explicitly selected transfer legs."""
    excluded = set(excluded)
    locations = {r['id']: r for r in snapshot['locations'] if r['active']}
    shore = next((r['id'] for r in locations.values() if r['kind'] == 'SHORE'), None)
    rows = [{**copy.deepcopy(r), 'kind': 'Passengers'} for r in personnel] + copy.deepcopy(materials)
    tasks, errors = [], []
    for row in rows:
        key = row['kind'] + ':' + str(row['id'])
        if key in excluded or row.get('is_void') or row.get('status') == 'Cancelled':
            continue
        if row['kind'] == 'Materials' and row.get('status') == 'Done':
            continue
        previous = 'Passengers:' + row['previous_task_id'] if row.get('previous_task_id') else None
        initial = (not previous and ((row['kind'] == 'Materials' and row.get('from_id') == shore) or
                   (row['kind'] == 'Passengers' and transfer_origin(row, snapshot))))
        if row['kind'] == 'Materials' and row.get('status') == 'On Board':
            initial = True
        problems = [p for p in row.get('issues', []) if p != 'Missing date']
        if row.get('to_id') not in locations or (not initial and row.get('from_id') not in locations):
            problems.append('Missing or inactive source / destination')
        if row.get('from_id') == row.get('to_id'):
            problems.append('Source and destination are identical')
        if not row.get('name') or (row['kind'] == 'Passengers' and not row.get('position')):
            problems.append('Missing name or position')
        errors.extend(f"{row.get('name', key)}: {p}" for p in problems)
        tasks.append({'key': key, 'from_id': row.get('from_id'), 'to_id': row.get('to_id'),
                      'initial': bool(initial), 'previous': previous, 'person_id': row.get('person_id') or row['id'],
                      'leg_index': leg_order(row)})
    tasks.sort(key=lambda t: t['key'])
    by_key = {t['key']: t for t in tasks}
    if len(by_key) != len(tasks):
        errors.append('Duplicate task identities')
    for task in tasks:
        if task['previous']:
            previous = by_key.get(task['previous'])
            if (not previous or previous['to_id'] != task['from_id'] or
                previous['person_id'] != task['person_id'] or previous['leg_index'] + 1 != task['leg_index']):
                errors.append(f"{task['key']}: preceding leg is missing, excluded or discontinuous")
        seen, current = set(), task
        while current and current['previous']:
            if current['key'] in seen:
                errors.append(f"{task['key']}: transfer chain contains a cycle")
                break
            seen.add(current['key']);current = by_key.get(current['previous'])
    normalized_pins = [{'id': p['id'], 'location_id': p.get('location_id', p.get('vessel_id'))} for p in pins]
    pin_ids = {p['id'] for p in normalized_pins}
    if len(pin_ids) != len(normalized_pins) or any(p['location_id'] not in locations for p in normalized_pins):
        errors.append('Invalid retained visit identities or locations')
    locked = copy.deepcopy(locked or {})
    pin_locations = {p['id']: p['location_id'] for p in normalized_pins}
    for key, assignment in locked.items():
        task = by_key.get(key)
        if not task:
            errors.append(f'{key}: a locked task is outside this plan')
            continue
        for side, location in (('pick', task['from_id']), ('drop', task['to_id'])):
            visit = assignment.get(side)
            if side in assignment and visit is None and (side == 'drop' or not task['initial']):
                errors.append(f'{key}: locked {side} is missing')
            if visit is not None and (visit not in pin_ids or pin_locations[visit] != location):
                errors.append(f'{key}: locked {side} does not match a retained visit')
        if task['initial'] and assignment.get('pick') is not None:
            errors.append(f'{key}: initially loaded task cannot have a locked pickup')
    problem = {'version': RULES_VERSION, 'tasks': tasks, 'shore_id': shore, 'pins': normalized_pins,
               'locked': locked, 'errors': list(dict.fromkeys(errors)),
               'reference_order': list(dict.fromkeys(reference_order)),
               'assumptions': ['Single transfer vessel', 'Sufficient capacity', 'No time windows',
                               'Sign-on passengers board at an actual port call before delivery']}
    problem['hash'] = digest(problem)
    return problem


def route_options(problem, task, stops):
    """Strict options, including real port pickups for linked later legs."""
    spec = next((t for t in problem['tasks'] if t['key'] == task['kind'] + ':' + str(task['id'])), None)
    if spec is None:
        return []
    picks = [None] if spec['initial'] else [s['id'] for s in stops if s['vessel_id'] == spec['from_id']]
    drops = [s['id'] for s in stops if s['vessel_id'] == spec['to_id']]
    order = {s['id']: i for i, s in enumerate(stops)}
    locked = problem.get('locked', {}).get(spec['key'], {})
    return [{'pick': p, 'drop': d} for p in picks for d in drops
            if (p is None or order[p] < order[d]) and
            all(side not in locked or locked[side] == value for side, value in (('pick', p), ('drop', d)))]


def solve(problem, *, cancelled=lambda: False, seconds=20.0, max_states=150000, progress=lambda value: None):
    """A* on (loaded, delivered, next retained visit). Every edge is a real call.

    Full legal actions are monotone with unbounded capacity. Locked actions wait for
    their retained visits. A later passenger leg only uses delivery BEFORE the call.
    """
    start_time = time.monotonic()
    if problem.get('errors'):
        return {'status': 'INPUT_INVALID', 'errors': problem['errors'], 'problem_hash': problem['hash']}
    tasks = problem['tasks'];index = {t['key']: i for i, t in enumerate(tasks)}
    all_done = (1 << len(tasks)) - 1
    initial = sum(1 << i for i, t in enumerate(tasks) if t['initial'])
    pins = problem['pins'];locked = problem['locked'];shore = problem['shore_id']
    preference={loc:i for i,loc in enumerate(problem.get('reference_order',[]))}
    locations = sorted({t['to_id'] for t in tasks} | {t['from_id'] for t in tasks if not t['initial']} |
                       {p['location_id'] for p in pins},key=lambda loc:(preference.get(loc,len(preference)),loc))
    start = (initial, 0, 0)
    def bound(state):
        needed = {}
        for i, task in enumerate(tasks):
            if not state[1] & (1 << i):needed[task['to_id']] = 1
            if not state[0] & (1 << i):needed[task['from_id']] = 1
        retained = {}
        for pin in pins[state[2]:]:retained[pin['location_id']] = retained.get(pin['location_id'], 0) + 1
        for loc, amount in retained.items():needed[loc] = max(needed.get(loc, 0), amount)
        return sum(n for loc, n in needed.items() if loc != shore), needed.get(shore, 0)

    distances = {start: (0, 0)};parents = {};queue = [(bound(start), (0, 0), 0, start)]
    serial = count(1);expanded = 0;last_progress = start_time
    incumbent = None

    def transition(state, location, pin_id, pin_progress):
        picked, delivered, q = state;old_delivered = delivered
        for i, task in enumerate(tasks):
            bit = 1 << i;lock = locked.get(task['key'], {})
            if (picked & bit and not delivered & bit and task['to_id'] == location and
                ('drop' not in lock or lock['drop'] == pin_id)):
                delivered |= bit
        for i, task in enumerate(tasks):
            bit = 1 << i;lock = locked.get(task['key'], {})
            ready = not task['previous'] or bool(old_delivered & (1 << index[task['previous']]))
            if (not picked & bit and task['from_id'] == location and ready and
                ('pick' not in lock or lock['pick'] == pin_id)):
                picked |= bit
        # All actions locked to a retained visit must be executable at that visit.
        if pin_id is not None:
            for key, lock in locked.items():
                bit = 1 << index[key]
                if lock.get('pick') == pin_id and not picked & bit:return None
                if lock.get('drop') == pin_id and not delivered & bit:return None
        return picked, delivered, pin_progress

    def reconstruct(state, cost, status, lower):
        edges = [];cursor = state
        while cursor != start:
            previous, location, pin_id = parents[cursor]
            edges.append((previous, cursor, location, pin_id));cursor = previous
        edges.reverse();visits = [];assignments = {t['key']: {'pick': None, 'drop': None} for t in tasks}
        for n, (before, after, location, pin_id) in enumerate(edges):
            visits.append({'location_id': location, 'retained_id': pin_id})
            for i, task in enumerate(tasks):
                bit = 1 << i
                if after[0] & bit and not before[0] & bit:assignments[task['key']]['pick'] = n
                if after[1] & bit and not before[1] & bit:assignments[task['key']]['drop'] = n
        actual_cost=[sum(v['location_id']!=shore for v in visits),sum(v['location_id']==shore for v in visits)]
        return {'status': status, 'problem_hash': problem['hash'], 'visits': visits, 'assignments': assignments,
                'cost': actual_cost, 'lower_bound': list(lower), 'errors': [], 'expanded_states': expanded,
                'elapsed_ms': round((time.monotonic() - start_time) * 1000)}

    while queue:
        if cancelled():return {'status': 'CANCELLED', 'errors': [], 'problem_hash': problem['hash']}
        lower, cost, _, state = heapq.heappop(queue)
        if distances.get(state) != cost:continue
        if state[1] == all_done and state[2] == len(pins):
            return reconstruct(state, cost, 'OPTIMAL', cost)
        if time.monotonic() - start_time >= seconds or len(distances) >= max_states:
            if incumbent:return reconstruct(incumbent[0], incumbent[1], 'FEASIBLE', lower)
            return {'status': 'NO_SOLUTION_YET', 'errors': ['Calculation limit reached; no complete solution yet.'],
                    'lower_bound': list(lower), 'problem_hash': problem['hash'], 'expanded_states': expanded}
        expanded += 1
        q = state[2]
        candidates = [(loc, None, q) for loc in locations]
        if q < len(pins):candidates.append((pins[q]['location_id'], pins[q]['id'], q + 1))
        for location, pin_id, nq in candidates:
            new = transition(state, location, pin_id, nq)
            if new is None or new == state:continue
            new_cost = (cost[0] + (location != shore), cost[1] + (location == shore))
            if new in distances and distances[new] <= new_cost:continue
            distances[new] = new_cost;parents[new] = (state, location, pin_id)
            h = bound(new)
            heapq.heappush(queue, ((new_cost[0] + h[0], new_cost[1] + h[1]), new_cost, next(serial), new))
            if new[1] == all_done and new[2] == len(pins) and (incumbent is None or new_cost < incumbent[1]):
                incumbent = (new, new_cost)
        now = time.monotonic()
        if now - last_progress > 0.25:
            progress({'expanded_states': expanded, 'elapsed_ms': round((now - start_time) * 1000)})
            last_progress = now
    return {'status': 'INFEASIBLE_PROVEN', 'errors': ['No complete route satisfies the retained visits and locked assignments.'],
            'problem_hash': problem['hash'], 'expanded_states': expanded}


def materialize(result, snapshot, original_route=()):
    """Allocate independent visit IDs once, preserving retained visits and useful old IDs."""
    from uuid import uuid4
    locations = {r['id']: r for r in snapshot['locations']}
    reserved = {v['retained_id'] for v in result['visits'] if v['retained_id'] is not None}
    used = set();stops = []
    for visit in result['visits']:
        identifier = visit['retained_id']
        if identifier is None:
            existing = next((s for s in original_route if s['vessel_id'] == visit['location_id'] and
                             s['id'] not in reserved and s['id'] not in used), None)
            identifier = existing['id'] if existing else 'plan:' + str(uuid4())
        used.add(identifier)
        stops.append({'id': identifier, 'vessel_id': visit['location_id'],
                      'vessel_name_snapshot': locations[visit['location_id']]['name'],
                      'optimizer_keep': visit['retained_id'] is not None})
    assignments = {key: {side: stops[n]['id'] if n is not None else None for side, n in values.items()}
                   for key, values in result['assignments'].items()}
    return stops, assignments
