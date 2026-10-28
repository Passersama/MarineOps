"""Reproducible architecture inventory and isolated history-growth benchmark."""
from pathlib import Path
import ast
import json
import os
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, UTC
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
os.environ['TMP'] = str(ROOT/'.tmp-build')
os.environ['TEMP'] = str(ROOT/'.tmp-build')


def measure(function):
    tracemalloc.start()
    started = time.perf_counter()
    function()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {'seconds': round(elapsed, 6), 'python_peak_bytes': peak}


def run(label):
    from test_dashboard import DashboardTests
    from cargo_track.personnel_service import encode
    fixture = DashboardTests(); fixture.setUp()
    try:
        saved = fixture.saved
        started = datetime(2026, 10, 1, tzinfo=UTC)
        rows = []
        for version in range(2, 502):
            value = json.loads(encode(saved))
            value.update(id=str(uuid4()), version=version)
            for stop in value['stops']:
                stop['comment'] = 'Historical stop instruction. ' * 35
            rows.append((value['id'], value['family_id'], version, value['status'], encode(value),
                         (started + timedelta(seconds=version)).isoformat()))
        fixture.personnel.db.executemany('INSERT INTO berth_versions VALUES(?,?,?,?,?,?)', rows)
        summary = measure(fixture.read)
        record = fixture.personnel.passenger(fixture.ids[0])
        update = measure(lambda: fixture.personnel.edit_crew_entry(
            record['id'], {**record, 'position': 'Chief Engineer'}, record['version']))
        fixture.personnel.rename_plan(fixture.list_id, 'Renamed', 'October roster')
        report = {'fixture': 'isolated fictional data', 'history_versions': 501,
                  'dashboard_read': summary, 'crew_edit_and_saved_sync': update,
                  'latest_version': fixture.personnel.berth_versions()[0]['version']}
    finally:
        fixture.tearDown()
    modules = []
    for path in sorted((ROOT/'src/cargo_track').glob('*.py')):
        source = path.read_text(encoding='utf-8'); tree = ast.parse(source)
        modules.append({'name': path.stem, 'lines': len(source.splitlines()), 'bytes': path.stat().st_size,
            'imports': sorted({node.module.split('.')[0] for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module})})
    report.update(source_modules=len(modules), source_lines=sum(m['lines'] for m in modules), modules=modules)
    graph={m['name']:m['imports'] for m in modules}
    cycles=[]
    def visit(name,trail):
        if name in trail:
            cycle=trail[trail.index(name):]+[name]
            if cycle not in cycles:cycles.append(cycle)
            return
        for dependency in graph.get(name,[]):visit(dependency,trail+[name])
    for name in graph:visit(name,[])
    core=('domain','schema','repository','service','personnel_import','personnel_routes',
          'personnel_cargo','personnel_service','berth_plan','berth_optimizer',
          'berth_optimization_validation','crew_plan_sync','plan_store','dashboard_data',
          'coordination','text_case','plan_state','view_state','excel_layout')
    qt_imports=[]
    for name in core:
        tree=ast.parse((ROOT/'src/cargo_track'/f'{name}.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('PySide6'):
                qt_imports.append(name)
            if isinstance(node,ast.Import) and any(n.name.startswith('PySide6') for n in node.names):
                qt_imports.append(name)
    report.update(import_cycles=cycles,core_qt_imports=qt_imports,core_modules_checked=list(core),
                  runtime_requirements=(ROOT/'requirements.txt').read_text(encoding='utf-8').splitlines())
    output = ROOT/'output/architecture-audit-1.2.5'/f'{label}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='modules'}, indent=2))


if __name__ == '__main__':
    run(sys.argv[1])
