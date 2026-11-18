"""Retain the unsuccessful object identity check and use the actual clean object."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
OUT=Path('/root/khicas-work/symbol-transaction-20261114')
SOURCE=OUT/'combined-clean-source'; PROOF=OUT/'solver-comment-equivalence'
SDK=Path('/root/.local/bin')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(SOURCE/'ksolve.cc')=='47cd33896a0b590bde45a00d2fa9b15966edbc71bef42481162c68888b597403'
assert digest(PROOF/'ksolve.o')==digest(PROOF/'byte-clean.o')
report=json.loads(Path('/root/khicas-work/giac-legacy-foundation-sh-v21/report.json').read_text())
flags=[f.replace('-flto=auto','-flto=1').replace('/root/khicas-work/giac-legacy-foundation-src-v21',str(SOURCE)) for f in report['flags']]+['-frandom-seed=0']
command=list(map(str,[report['compiler'],*flags,'-c',SOURCE/'ksolve.cc','-o',PROOF/'ksolve.o']))
env=dict(os.environ,LD_LIBRARY_PATH='/opt/khicas-host/lib/x86_64-linux-gnu')
archives=[]
for profile in ('static','formal'):
    original=OUT/('combined-'+profile)/'libgiac.a'
    folder=OUT/('combined-clean-'+profile); folder.mkdir()
    target=folder/'libgiac.a'; shutil.copy2(original,target)
    cmd=list(map(str,[SDK/'sh-elf-gcc-ar','rcs',target,PROOF/'ksolve.o']))
    p=subprocess.run(cmd,capture_output=True,env=env,timeout=60)
    assert p.returncode==0,p.stderr
    names=subprocess.check_output([SDK/'sh-elf-ar','t',original]).splitlines()
    assert names==subprocess.check_output([SDK/'sh-elf-ar','t',target]).splitlines()
    for name in names:
        if name==b'ksolve.o': continue
        assert subprocess.check_output([SDK/'sh-elf-ar','p',original,name.decode()])==subprocess.check_output([SDK/'sh-elf-ar','p',target,name.decode()])
    archives.append(dict(profile=profile,archive=str(target),archive_sha256=digest(target),command=cmd,
                         original_18a_archive_sha256=digest(original),only_ksolve_member_replaced=True))
record=dict(final_source_sha256=digest(SOURCE/'ksolve.cc'),clean_object_sha256=digest(PROOF/'byte-clean.o'),
    measured_seed0_object_sha256=digest(PROOF/'measured.o'),object_comparison_identical=False,
    compile_command=command,archives=archives,
    note='Complete object-byte comparison failed; retain both objects and run necessary SH checks on the clean archives. No earlier results are relabelled.')
(OUT/'byteclean-build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
