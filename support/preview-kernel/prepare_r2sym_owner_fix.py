"""Guard the three sibling rational-to-symbolic construction owners."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

BASE_SHA="49755649db352f525632d0f344ec7cf66c172f73fa502acfedaddbb9002b5915"

def prepare(source,output):
    raw=source.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==BASE_SHA,"Unexpected ksym2poly.cc"
    text=raw.decode("latin1")
    updated=text.replace('#include <string>','#include <string>\n#include <memory>',1)
    opening=updated.index('  gen r2sym(const gen & e,const index_m & i,const vecteur & l,GIAC_CONTEXT){')
    ending=updated.index('  static gen r2sym(const gen & p, const const_iterateur & lt,',opening)
    part=updated[opening:ending]
    assert part.count('    ref_vecteur * res=new_ref_vecteur(0);')==3
    part=part.replace('    ref_vecteur * res=new_ref_vecteur(0);',
        '    std::unique_ptr<ref_vecteur,void (*)(ref_vecteur *)> owner(new_ref_vecteur(0),&delete_ref_vecteur);\n    ref_vecteur * res=owner.get();')
    part=part.replace('      delete_ref_vecteur(res);\n      return e;','      return e;',1)
    part=part.replace('    return niceprod(res,negatif);','    return niceprod(owner.release(),negatif);',1)
    part=part.replace('      delete res;\n      return tmp;','      return tmp;',1)
    part=part.replace('    return symbolic(at_plus,gen(res,_SEQ__VECT));','    return symbolic(at_plus,gen(owner.release(),_SEQ__VECT));',1)
    vector_start=part.index('  gen r2sym(const vecteur & v,const vecteur & l,GIAC_CONTEXT){')
    part=part[:vector_start]+part[vector_start:].replace('    return res;\n  }','    return gen(owner.release());\n  }',1)
    updated=updated[:opening]+part+updated[ending:]
    output.mkdir(exist_ok=True,parents=True)
    target=output/"ksym2poly.cc"
    assert source.resolve()!=target.resolve()
    target.write_bytes(updated.encode("latin1"))
    (output/"r2sym-owner.patch").write_text(''.join(difflib.unified_diff(text.splitlines(True),updated.splitlines(True),fromfile="accepted/ksym2poly.cc",tofile="preview/ksym2poly.cc")))
    binding=dict(source_sha256=BASE_SHA,candidate_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                 scope="Three sibling r2sym ref_vecteur owners; no mathematical rewrite")
    (output/"r2sym-owner-binding.json").write_text(json.dumps(binding,indent=2)+"\n")
    return target

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    prepare(args.source,args.output)
