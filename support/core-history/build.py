"""Single-process build; all writable outputs and staged inputs are private."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
OUT=Path('/root/khicas-work/symbol-transaction-20261114')
SOURCE=OUT/'source'
INPUT=OUT/'inputs'
OBJECTS=OUT/'objects'
OBJECTS24=OUT/'objects-soft24'
OLD=Path('/root/khicas-work/formal-leaf-runtime-20261114')
OLDHERE=Path('/root/project/audit/formal-leaf-runtime-20261114')
BASE=Path('/root/khicas-work/giac-legacy-foundation-src-v21')
UI=Path('/root/khicas-work/giac-legacy-foundation-ui-v21')
REPORT=Path('/root/khicas-work/giac-legacy-foundation-sh-v21/report.json')
LEAF=Path('/root/khicas-work/formal-leaf-20261114')
SDK=Path('/root/.local/bin')
env=dict(os.environ,LD_LIBRARY_PATH='/opt/khicas-host/lib/x86_64-linux-gnu')
commands=[]
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads(REPORT.read_text())
flags=[x.replace('-flto=auto','-flto=1').replace(str(BASE),str(SOURCE)) for x in report['flags']]

def run(label,cmd,timeout=180):
    cmd=list(map(str,cmd)); commands.append(cmd); print(label,flush=True)
    r=subprocess.run(cmd,capture_output=True,env=env,timeout=timeout)
    (OUT/(label+'.log')).write_bytes(r.stdout+r.stderr)
    if r.returncode: raise RuntimeError((label,r.returncode,r.stderr.decode()[-3500:]))
    return r.stdout

def copy(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists(): assert digest(dest)==digest(src),(src,dest)
    else: shutil.copy2(src,dest)
    return dest

def objects():
    OBJECTS.mkdir(exist_ok=True)
    for name in ('kglobal','kprog'):
        run(name+'-compile',[report['compiler'],*flags,'-c',SOURCE/(name+'.cc'),'-o',OBJECTS/(name+'.o')])
    for name,test in [('bridge24',False),('bridge24_test',True)]:
        run(name+'-compile',[report['compiler'],*flags,'-I'+str(INPUT/'project/src'),
            '-DKHICAS_UI_PLOTS=1',*(['-DGIAC_MEMORY_TEST'] if test else []),
            '-c',OUT/'giac_bridge.cc','-o',OBJECTS/(name+'.o')])
    for label,original in [('static',UI/'libgiac.a'),('formal',LEAF/'core/libgiac.a')]:
        archive=OUT/label/'libgiac.a'; archive.parent.mkdir(exist_ok=True)
        assert not archive.exists(),'Do not overwrite an archive already used by a link'
        shutil.copy2(original,archive)
        run(label+'-archive',[SDK/'sh-elf-ar','r',archive,OBJECTS/'kglobal.o',OBJECTS/'kprog.o'])
        before=run(label+'-before-members',[SDK/'sh-elf-ar','t',original]).splitlines()
        after=run(label+'-after-members',[SDK/'sh-elf-ar','t',archive]).splitlines()
        assert before==after and len(before)==39
        rows=[]
        for name in before:
            old=run(label+'-original-'+name.decode(),[SDK/'sh-elf-ar','p',original,name.decode()])
            new=run(label+'-candidate-'+name.decode(),[SDK/'sh-elf-ar','p',archive,name.decode()])
            changed=name in (b'kglobal.o',b'kprog.o')
            assert changed or old==new,name
            rows.append(dict(member=name.decode(),changed=changed,
                original_sha256=hashlib.sha256(old).hexdigest(),candidate_sha256=hashlib.sha256(new).hexdigest()))
        (OUT/(label+'-archive.json')).write_text(json.dumps(dict(original=str(original),
            original_sha256=digest(original),candidate=str(archive),candidate_sha256=digest(archive),members=rows),indent=2)+'\n')
    (OUT/'objects.json').write_text(json.dumps(dict(commands=commands,
        source_sha256={str(p):digest(p) for p in [SOURCE/'kglobal.cc',SOURCE/'kprog.cc',
            SOURCE/'giac_symbol_transaction.h',SOURCE/'giac_symbol_operations.inc',OUT/'giac_bridge.cc']},
        object_sha256={str(p):digest(p) for p in OBJECTS.glob('*.o')}),indent=2)+'\n')

def stage():
    INPUT.mkdir(exist_ok=True); OBJECTS.mkdir(exist_ok=True)
    bindings={}
    def cp(src,dst):
        copy(src,dst); bindings[str(dst)]=dict(original=str(src),sha256=digest(src))
    for folder in ('src','tests'):
        for p in (Path('/root/project')/folder).glob('*'):
            if p.is_file(): cp(p,INPUT/'project'/folder/p.name)
    for p in UI.glob('*.o'): cp(p,INPUT/'ui'/p.name)
    cp(REPORT,INPUT/'report.json')
    cp(Path('/root/khicas-work/cas-32k-20261114/objects/giac_bootstrap.o'),OBJECTS/'giac_bootstrap.o')
    for folder in ('v21-transactions','v21-plot'):
        for p in (Path('/root/runtime-trim-20261114/regression')/folder).glob('*.o'):
            cp(p,INPUT/'regression'/folder/p.name)
    runtime=Path('/root/khicas-work/giac-startup-audit/giii13-fullrom')
    for pattern in ('*.h','*.o'):
        for p in runtime.glob(pattern): cp(p,INPUT/'runtime'/p.name)
    cp(Path('/root/khicas-work/giac-size-next-support/libtommath-memory.a'),INPUT/'libtommath-memory.a')
    cp(Path('/root/khicas-work/giac-stdlib-unwind-v4/build/sh3eb-elf/m4-nofpu/libstdc++-v3/src/.libs/libstdc++.a'),INPUT/'libstdc++.a')
    for p in (LEAF/'module').glob('*'):
        if p.is_file(): cp(p,INPUT/'leaf/module'/p.name)
    for name in ('runtime.o','entry.o','cas-cli.o'): cp(OLD/name,INPUT/name)
    for name in ('target-loader.cc','native-cases.inc','module.ld','oracle-main.cc','unwind-module.c',
                 'formal-window.h','window-runtime.inc','loader-suffix.inc','transactions.cc'):
        cp(OLDHERE/name,INPUT/'fixtures-base'/name)
    for p in (OLDHERE/'source').glob('*'):
        if p.is_file(): cp(p,INPUT/'fixtures-base/source'/p.name)
    cp(OLDHERE/'build.py',INPUT/'original-driver.py')
    (OUT/'staged-inputs.json').write_text(json.dumps(bindings,indent=2)+'\n')

def index_archives():
    records=[]
    for label in ('static','formal'):
        original=OUT/label/'libgiac.a'
        target=OUT/(label+'-indexed')/'libgiac.a'
        copy(original,target)
        run(label+'-plugin-index',[SDK/'sh-elf-gcc-ar','s',target])
        records.append(dict(profile=label,unindexed_archive_sha256=digest(original),
            indexed_archive_sha256=digest(target),indexed_archive=str(target),
            note='Use GCC LTO plugin when rebuilding archive index; initial plain-ar index caused unresolved symbols before any target ran'))
    (OUT/'archive-index-correction.json').write_text(json.dumps(records,indent=2)+'\n')

def bridge24():
    OBJECTS24.mkdir(exist_ok=True)
    source=OUT/'giac_bridge24.cc'
    assert 'const size_t total_heap_limit = 24 * 1024;' in source.read_text()
    assert 'static_assert(total_heap_limit == 24 * 1024, "Calculator CAS tracking must remain 24 KiB");' in source.read_text()
    copy(OBJECTS/'giac_bootstrap.o',OBJECTS24/'giac_bootstrap.o')
    for name,test in [('bridge24',False),('bridge24_test',True)]:
        assert not (OBJECTS24/(name+'.o')).exists()
        run(name+'-corrected-compile',[report['compiler'],*flags,'-I'+str(INPUT/'project/src'),
            '-DKHICAS_UI_PLOTS=1',*(['-DGIAC_MEMORY_TEST'] if test else []),
            '-c',source,'-o',OBJECTS24/(name+'.o')])
    (OUT/'bridge24-objects.json').write_text(json.dumps(dict(source_sha256=digest(source),
        tracker_limit_bytes=24576,application_arena_bytes=32768,
        object_sha256={str(p):digest(p) for p in OBJECTS24.glob('*.o')},commands=commands),indent=2)+'\n')

def link(profile):
    clean=profile.startswith('clean-')
    selected=profile[len('clean-'):] if clean else profile
    combined=selected.startswith('combined-')
    kind=selected[len('combined-'):] if combined else selected
    folder=OUT/profile; assert not folder.exists(),'Each link gets a fresh output directory'
    folder.mkdir()
    fixtures=folder/'fixtures'; shutil.copytree(INPUT/'fixtures-base',fixtures)
    if kind=='static-cli':
        (fixtures/'oracle-main.cc').write_text('#define main module_cli_run\nextern "C" {\n#include "cas_cli.c"\n}\n#undef main\nextern "C" int khicas_cli_main(){ return module_cli_run(); }\n')
        mode='oracle'
    elif kind.startswith('static-unit') or kind in ('static-symbols','static-strict'):
        target='symbol-unit.cc' if kind.startswith('static-unit') else {'static-symbols':'symbol-failures.cc','static-strict':'transactions.cc'}[kind]
        if target!='transactions.cc': copy(HERE/target,fixtures/target)
        (fixtures/'oracle-main.cc').write_text('#define KHICAS_LAYOUT_ENTRY 1\n#include "'+target+'"\n')
        mode='oracle'
    elif kind=='formal-cli': mode='cli'
    elif kind=='formal-plot': mode='plot'
    elif kind.startswith('formal-strict') or kind=='formal-symbols':
        if kind.endswith('symbols'): shutil.copy2(HERE/'symbol-failures.cc',fixtures/'transactions.cc')
        mode='transactions'
    else: raise ValueError(profile)
    for name in ('runtime.o','entry.o','cas-cli.o'): copy(INPUT/name,folder/name)
    ui=folder/'ui'; ui.mkdir()
    for p in (INPUT/'ui').glob('*'): copy(p,ui/p.name)
    static_archive='combined-clean-static' if clean else 'combined-static' if combined else 'static-indexed'
    formal_archive='combined-clean-formal' if clean else 'combined-formal' if combined else 'formal-indexed'
    copy(OUT/static_archive/'libgiac.a',ui/'libgiac.a')
    leaf=folder/'leaf'; shutil.copytree(INPUT/'leaf',leaf)
    copy(OUT/formal_archive/'libgiac.a',leaf/'core/libgiac.a')
    text=(INPUT/'original-driver.py').read_text()
    replacements={
        'HERE=Path(__file__).resolve().parent':f'HERE=Path({str(fixtures)!r})',
        "ROOT=Path('/root/project')":f'ROOT=Path({str(INPUT/"project")!r})',
        "OUT=Path('/root/khicas-work/formal-leaf-runtime-20261114')":f'OUT=Path({str(folder)!r})',
        "LEAF=Path('/root/khicas-work/formal-leaf-20261114')":f'LEAF=Path({str(leaf)!r})',
        "UI=Path('/root/khicas-work/giac-legacy-foundation-ui-v21')":f'UI=Path({str(ui)!r})',
        "TEST=Path('/root/runtime-trim-20261114/regression/v21-transactions')":f'TEST=Path({str(INPUT/"regression/v21-transactions")!r})',
        "CAP=Path('/root/khicas-work/cas-32k-20261114/objects')":f'CAP=Path({str(OBJECTS24)!r})',
        "RUNTIME=Path('/root/khicas-work/giac-startup-audit/giii13-fullrom')":f'RUNTIME=Path({str(INPUT/"runtime")!r})',
        "TOM=Path('/root/khicas-work/giac-size-next-support/libtommath-memory.a')":f'TOM=Path({str(INPUT/"libtommath-memory.a")!r})',
        "STD=Path('/root/khicas-work/giac-stdlib-unwind-v4/build/sh3eb-elf/m4-nofpu/libstdc++-v3/src/.libs/libstdc++.a')":f'STD=Path({str(INPUT/"libstdc++.a")!r})',
        "(SH/'report.json')":f'Path({str(INPUT/"report.json")!r})',
        "Path('/root/runtime-trim-20261114/regression/v21-plot')":f'Path({str(INPUT/"regression/v21-plot")!r})',
        "Path('/root/runtime-trim-20261114/regression/v21-plot/main.o')":f'Path({str(INPUT/"regression/v21-plot/main.o")!r})',
    }
    for old,new in replacements.items(): assert old in text,old; text=text.replace(old,new)
    driver=folder/'driver.py'; driver.write_text(text)
    spec=importlib.util.spec_from_file_location('private_'+profile.replace('-','_'),driver)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    selected_source=OUT/'combined-clean-source' if clean else OUT/'combined-source' if combined else SOURCE
    module.flags=[f.replace(str(SOURCE),str(selected_source)) for f in flags]
    module.link(mode)
    record=dict(profile=profile,mode=mode,driver_sha256=digest(driver),
        actual_bridge_source_sha256=digest(OUT/'giac_bridge24.cc'),actual_tracker_limit_bytes=24576,
        physical_arena_bytes=32768,parent_test_storage_bytes=33024,independent_window_bytes=8192,
        fixtures_sha256={str(p.relative_to(fixtures)):digest(p) for p in fixtures.rglob('*') if p.is_file()})
    (folder/'profile.json').write_text(json.dumps(record,indent=2)+'\n')

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='stage': stage()
    elif mode=='objects': objects()
    elif mode=='index': index_archives()
    elif mode=='bridge24': bridge24()
    else: link(mode)
