"""Verify current artifacts independently of historical packages and local logs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cargo_track import __version__


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def code_value(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,tuple(code_value(v) for v in value.co_consts),value.co_names,
                value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
                value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags)
    if isinstance(value,tuple):return tuple(code_value(v) for v in value)
    return value


def verify_current(root=ROOT):
    folder=root/'dist/MarineOps';exe=folder/'MarineOps.exe'
    portable=root/f'release/MarineOps-{__version__}-Windows-x64.zip'
    setup=root/f'release/MarineOps-Setup-{__version__}.exe'
    obsolete={'MarineOps/'+n for n in ('AUTO-PLANNING.txt','TEXT-CASING.txt','CREW-SYNC.txt')}
    for path in (exe,portable,setup):
        if not path.is_file():raise ValueError('Current artifact is missing: '+str(path))
    with zipfile.ZipFile(portable) as archive:
        names=archive.namelist()
        expected={'MarineOps/'+p.relative_to(folder).as_posix():p for p in folder.rglob('*') if p.is_file()}
        if len(names)!=len(set(names)) or set(names)!=set(expected)|{'README.txt'}:
            raise ValueError('Portable file inventory differs from the current build.')
        if obsolete & set(names):raise ValueError('Superseded release notes remain in the current package.')
        if [n for n in names if n.lower().endswith('.exe')]!=['MarineOps/MarineOps.exe']:
            raise ValueError('Unexpected executable in the current package.')
        if any(n.lower().endswith(('.db','.sqlite','.sqlite3','.bak','.log')) for n in names):
            raise ValueError('Business data or runtime logs must not be packaged.')
        for name,path in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=sha(path):
                raise ValueError('Portable content differs from the current build: '+name)
        if archive.testzip() is not None:raise ValueError('Portable ZIP integrity failed.')
        for name in ('marineops-symbol.png','marineops.ico'):
            if archive.read('MarineOps/_internal/assets/branding/'+name)!=(root/'assets/branding'/name).read_bytes():
                raise ValueError('Packaged branding differs from source.')
        if archive.read('MarineOps/_internal/assets/help/user-guide.html')!=(root/'assets/help/user-guide.html').read_bytes():
            raise ValueError('Packaged Help differs from source.')
        if not any(n.endswith('/Manrope-OFL.txt') for n in names):raise ValueError('Manrope font license missing.')
        if any('/assets/fonts/Inter-' in n for n in names):raise ValueError('Obsolete Inter fonts remain in the package.')
    if portable.read_bytes() not in setup.read_bytes():raise ValueError('Installer contains a different payload.')
    container=CArchiveReader(str(exe))
    pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
    modules=[];manifest={}
    for source in sorted((root/'src/cargo_track').glob('*.py')):
        manifest[source.relative_to(root).as_posix()]=sha(source)
        if source.stem=='pyi_rth_dll_dirs':continue
        module='cargo_track' if source.stem=='__init__' else 'cargo_track.'+source.stem
        if code_value(compile(source.read_text(encoding='utf-8'),'comparison','exec'))!=code_value(pyz.extract(module)):
            raise ValueError('Compiled module differs from source: '+module)
        modules.append(module)
    return {'result':'PASS','version':__version__,'scope':'current-package static verification',
        'zip_integrity':'PASS','portable_matches_clean_build':True,'installer_contains_exact_portable_payload':True,
        'compiled_modules_match_source':modules,'source_manifest':manifest,
        'artifacts':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (exe,portable,setup)},
        'upgrade':{'status':'NOT_RUN','reason':'Run the separate upgrade check with an explicit previous version.'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-log',type=Path)
    parser.add_argument('--native-report',type=Path)
    parser.add_argument('--package-report',type=Path,help='Separate installed/portable upgrade runtime report')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=verify_current()
    if args.test_log:
        value=args.test_log.read_text(encoding='utf-8-sig')
        matches=re.findall(r'Ran (\d+) tests in ([\d.]+)s',value)
        if not matches or not re.search(r'\nOK(?: \(skipped=\d+\))?\s*\Z',value):
            raise ValueError('The supplied regression log did not finish successfully.')
        skipped=re.findall(r'OK \(skipped=(\d+)\)',value)
        report.update(full_regression_tests=int(matches[-1][0]),skipped_tests=int(skipped[-1]) if skipped else 0,
                      test_log_sha256=sha(args.test_log))
        report['passed_tests']=report['full_regression_tests']-report['skipped_tests']
    if args.native_report:
        native=json.loads(args.native_report.read_text(encoding='utf-8-sig'))
        if native.get('result')!='PASS' or native.get('version')!=__version__:raise ValueError('Native report is not for this version.')
        report['native_ui']=native;report['native_report_sha256']=sha(args.native_report)
    if args.package_report:
        runtime=json.loads(args.package_report.read_text(encoding='utf-8-sig'))
        expected=report['artifacts']['MarineOps.exe']['sha256']
        if (runtime.get('version')!=__version__ or runtime.get('upgrade')!='PASS'
                or len(runtime.get('packages',[]))!=2
                or not all(p.get('business_data_unchanged') and p.get('clean_close')=='PASS'
                           and p.get('sha256','').lower()==expected for p in runtime['packages'])):
            raise ValueError('Upgrade report does not validate this executable.')
        report['upgrade']={'status':'PASS','report_sha256':sha(args.package_report)}
        report['packages']=runtime
    output=args.output or ROOT/f'release/MarineOps-release-validation-{__version__}.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'result':report['result'],'version':__version__,'upgrade':report['upgrade']['status'],'report':str(output)}))


if __name__=='__main__':main()
