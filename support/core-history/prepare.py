"""Create a private v21 source overlay; never modify production or old audit."""
from pathlib import Path
import hashlib,json,shutil,difflib
HERE=Path(__file__).resolve().parent
BASE=Path('/root/khicas-work/giac-legacy-foundation-src-v21')
OUT=Path('/root/khicas-work/symbol-transaction-20261114')
SOURCE=OUT/'source'
ROOT=Path('/root/project')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OUT.mkdir(exist_ok=True,parents=True)
if SOURCE.exists():
    assert not (OUT/'preparation.json').exists(),'Keep each prepared source frozen'
    assert all(digest(SOURCE/p.relative_to(BASE))==digest(p) for p in BASE.rglob('*') if p.is_file())
else:
    shutil.copytree(BASE,SOURCE)
manifest=dict(base=str(BASE),
    base_report_sha256=digest(Path('/root/khicas-work/giac-legacy-foundation-sh-v21/report.json')),
    changes={})

def replace_once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new,1)

for name in ('giac_symbol_transaction.h','giac_symbol_operations.inc'):
    shutil.copy2(HERE/name,SOURCE/name)

patches=[]
for name in ('kglobal.cc','kprog.cc'):
    old=(BASE/name).read_text(); text=old
    text=replace_once(text,'#include "giac_memory.h"',
                      '#include "giac_memory.h"\n#include "giac_symbol_transaction.h"')
    if name=='kglobal.cc':
        text=replace_once(text,'\tsyms()[s] = res;','\tSymbolTransaction::insert(s,res);')
        text=replace_once(text,'\tsyms()[it->_IDNTptr->name()] = *it;',
                          '\tSymbolTransaction::insert(it->_IDNTptr->name(),*it);')
        text=replace_once(text,'    initialisation_done(contextptr)=true;',
            '    if (!contextptr || !contextptr->globalptr)\n'
            '      SymbolTransaction::record_global_initialisation(initialisation_done(contextptr));\n'
            '    initialisation_done(contextptr)=true;')
        text=replace_once(text,'  gen make_symbolic(const gen & op,const gen & args){',
            '#include "giac_symbol_operations.inc"\n\n  gen make_symbolic(const gen & op,const gen & args){')
    else:
        text=replace_once(text,'\t  *it = *(new identificateur(s));\n\t  syms()[s] = *it;',
            '\t  *it = identificateur(s);\n\t  SymbolTransaction::insert(s,*it);')
    (SOURCE/name).write_text(text)
    manifest['changes'][name]=dict(before_sha256=digest(BASE/name),after_sha256=digest(SOURCE/name))
    patches.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),
                                     fromfile='v21/'+name,tofile='candidate/'+name))

bridge=ROOT/'src/giac_bridge.cc'
old=bridge.read_text(); text=old
text=replace_once(text,'#include "giac_heap_transaction.h"',
                 '#include "giac_heap_transaction.h"\n#include "giac_symbol_transaction.h"')
text=replace_once(text,'        giac::HeapTransaction heaps;',
                 '        giac::SymbolTransaction symbols;\n        giac::HeapTransaction heaps;')
text=replace_once(text,'        heaps.commit();','        heaps.commit();\n        symbols.commit();')
(OUT/'giac_bridge.cc').write_text(text)
manifest['changes']['giac_bridge.cc']=dict(before_sha256=digest(bridge),after_sha256=digest(OUT/'giac_bridge.cc'))
patches.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),
                                 fromfile='production/giac_bridge.cc',tofile='candidate/giac_bridge.cc'))
(OUT/'source.patch').write_text(''.join(patches))
(OUT/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
