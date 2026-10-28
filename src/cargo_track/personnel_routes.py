"""Shared personnel route semantics; no execution state is inferred."""
from .personnel_import import key, PersonnelError


def transfer_name(snapshot):
    return snapshot.get('plan_transfer_vessel', snapshot['settings'].get('transfer_vessel_name', '')).strip()


def transfer_origin(task, snapshot):
    if task.get('kind', 'Passengers') != 'Passengers':
        return False
    name = transfer_name(snapshot)
    if not name:
        return False
    if key(task.get('from_name')) == key(name):
        return True
    matches = [r for r in snapshot['locations'] if r['active'] and key(r['name']) == key(name)]
    return len(matches) == 1 and task.get('from_id') == matches[0]['id']


def person_identity(task):
    return task.get('person_id') or task['id']


def leg_order(task):
    # Pre-multi-leg records have no index, and older snapshots serialized it as
    # an empty string. Normalize at read time without rewriting saved versions.
    value = task.get('leg_index')
    if value is None or (isinstance(value, str) and not value.strip()):
        return 1
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdecimal() and int(value.strip()) > 0:
        return int(value.strip())
    raise PersonnelError('Invalid passenger leg number. Review the personnel transfer chain.')


def suggested_leg_order(tasks):
    """Suggest a connected trail; the user still reviews and may reorder it."""
    if not tasks:
        return []
    incoming, outgoing, edges = {}, {}, {}
    for task in reversed(tasks):
        source, target = task.get('from_id'), task.get('to_id')
        if source is None or target is None:
            return list(tasks)
        outgoing[source] = outgoing.get(source, 0) + 1
        incoming[target] = incoming.get(target, 0) + 1
        edges.setdefault(source, []).append(task)
    starts = [node for node in outgoing if outgoing[node] - incoming.get(node, 0) == 1]
    ids = {t['id'] for t in tasks}
    root = next((t for t in tasks if t.get('previous_task_id') not in ids), tasks[0])
    start = starts[0] if len(starts) == 1 else root['from_id']
    nodes, pending, result = [start], [], []
    while nodes:
        choices = edges.get(nodes[-1], [])
        if choices:
            task = choices.pop()
            nodes.append(task['to_id']);pending.append(task)
        else:
            nodes.pop()
            if pending:result.append(pending.pop())
    result.reverse()
    if len(result) != len(tasks) or any(a['to_id'] != b['from_id'] for a, b in zip(result, result[1:])):
        return list(tasks)
    return result
