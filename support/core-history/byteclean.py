"""Prove a comment-only source correction produces identical LTO objects."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
OUT=Path('/root/khicas-work/symbol-transaction-20261114')
SOURCE=OUT/'combined-clean-source'
OLD=OUT/'combined-source'
CLEAN=Path('/root/project/audit/solver-id-lifetime-20261114/promotion/replay/ksolve.cc')
SDK=Path('/root/.local/bin')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(OLD/'ksolve.cc')=='18a9405ad62988417bf3101da0231d20f9ab923e91ffd9f0cade2b7978e68f60'
assert digest(CLEAN)=='47cd33896a0b590bde45a00d2fa9b15966edbc71bef42481162c68888b597403'
assert not SOURCE.exists()
shutil.copytree(OLD,SOURCE)
PROOF=OUT/'solver-comment-equivalence'; PROOF.mkdir()
report=json.loads(Path('/root/khicas-work/giac-legacy-foundation-sh-v21/report.json').read_text())
flags=[f.replace('-flto=auto','-flto=1').replace('/root/khicas-work/giac-legacy-foundation-src-v21',str(SOURCE)) for f in report['flags']]
flags+=['-frandom-seed=0']
member=PROOF/'ksolve.o'
command=list(map(str,[report['compiler'],*flags,'-c',SOURCE/'ksolve.cc','-o',member]))
env=dict(os.environ,LD_LIBRARY_PATH='/opt/khicas-host/lib/x86_64-linux-gnu')
records=[]
for label,path in [('measured',OLD/'ksolve.cc'),('byte-clean',CLEAN)]:
    shutil.copy2(path,SOURCE/'ksolve.cc')
    shutil.copy2(path,PROOF/(label+'-ksolve.cc'))
    print(label+'-compile',flush=True)
    p=subprocess.run(command,capture_output=True,env=env,timeout=180)
    (PROOF/(label+'.log')).write_bytes(p.stdout+p.stderr)
    assert p.returncode==0,p.stderr.decode()[-3000:]
    shutil.copy2(member,PROOF/(label+'.o'))
    records.append(dict(label=label,source_sha256=digest(path),object_sha256=digest(member),object_bytes=member.stat().st_size))
assert (PROOF/'measured.o').read_bytes()==(PROOF/'byte-clean.o').read_bytes(),records
archives=[]
for profile in ('static','formal'):
    original=OUT/('combined-'+profile)/'libgiac.a'
    folder=OUT/('combined-clean-'+profile); folder.mkdir()
    target=folder/'libgiac.a'; shutil.copy2(original,target)
    cmd=list(map(str,[SDK/'sh-elf-gcc-ar','rcs',target,member]))
    p=subprocess.run(cmd,capture_output=True,env=env,timeout=60)
    assert p.returncode==0,p.stderr
    archives.append(dict(profile=profile,archive=str(target),archive_sha256=digest(target),command=cmd,
                         original_measured_archive_sha256=digest(original)))
record=dict(same_path_same_flags_same_output_path=True,fixed_random_seed=0,
    comment_only_object_bytes_identical=True,records=records,compile_command=command,
    archives=archives,final_source_sha256=digest(SOURCE/'ksolve.cc'),
    caveat='The preserved earlier 18a combination used the default random seed. These new archives use the exact equal seed-0 measured/clean objects and are separately identified; no earlier ELF is relabelled.')
(OUT/'byteclean-build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
