"""Combine the two reviewed repairs, replacing only a second core member."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from prepare_r2sym_owner_fix import prepare

ROOT=Path("/root/khicas-work/preview-kernel-20261117/kernel")
OUT=ROOT/"build-v3"
BASE=Path("/root/khicas-work/symbol-transaction-20261114")
CLI=BASE/"clean-combined-static-cli"
ORIGINAL=BASE/"combined-clean-static/libgiac.a"
V2=ROOT/"build-v2"
assert not OUT.exists(),"Use a fresh candidate directory"
OUT.mkdir()
EVIDENCE=OUT/"evidence"
EVIDENCE.mkdir()
SOURCE=OUT/"source"
shutil.copytree(V2/"source",SOURCE)
prepare(BASE/"combined-clean-source/ksym2poly.cc",SOURCE)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original_sha=digest(ORIGINAL)
assert original_sha=="1b127e8f3e44cdb7452ea5d8bad8e792d1a6ea4bfa6962a14910d2598028e098"
env=dict(os.environ,LD_LIBRARY_PATH="/opt/khicas-host/lib/x86_64-linux-gnu")
commands=[]
def run(label,command,timeout=600,input=None,check=True):
    command=list(map(str,command))
    commands.append(dict(label=label,command=command))
    print(label,flush=True)
    result=subprocess.run(command,capture_output=True,env=env,timeout=timeout,input=input)
    (EVIDENCE/(label+".stdout")).write_bytes(result.stdout)
    (EVIDENCE/(label+".stderr")).write_bytes(result.stderr)
    if check and result.returncode: raise RuntimeError((label,result.returncode,result.stderr.decode(errors="replace")[-2500:]))
    return result

report=json.loads((BASE/"inputs/report.json").read_text())
flags=[p.replace("-flto=auto","-flto=1") for p in report["flags"]]
flags=["-I"+str(SOURCE) if p=="-I"+report["source"] else p for p in flags]
object_file=OUT/"ksym2poly.o"
run("owner-compile",[report["compiler"],*flags,"-frandom-seed=0","-c",SOURCE/"ksym2poly.cc","-o",object_file])
archive=OUT/"libgiac-kernel-preview.a"
shutil.copy2(V2/"libgiac-dirac-preview.a",archive)
ar="/root/.local/bin/sh-elf-gcc-ar"
run("archive-replace",[ar,"rcs",archive,object_file])
members=subprocess.check_output([ar,"t",str(ORIGINAL)],env=env).decode().splitlines()
assert len(members)==39 and subprocess.check_output([ar,"t",str(archive)],env=env).decode().splitlines()==members
old_hashes={n:hashlib.sha256(subprocess.check_output([ar,"p",str(ORIGINAL),n],env=env)).hexdigest() for n in members}
new_hashes={n:hashlib.sha256(subprocess.check_output([ar,"p",str(archive),n],env=env)).hexdigest() for n in members}
changed=[n for n in members if old_hashes[n]!=new_hashes[n]]
assert changed==["ksym2poly.o","kintgab.o"],changed
reference=json.loads((CLI/"oracle-build.json").read_text())
command=list(reference["commands"][0])
entry=Path(__file__).with_name("combined_dirac_entry.cc")
entry_object=OUT/"combined-entry.o"
command[command.index("-c")+1]=str(entry)
command[command.index("-o")+1]=str(entry_object)
command=["-I"+str(SOURCE) if p=="-I"+str(BASE/"combined-clean-source") else p for p in command]
run("entry-compile",command)
executable=OUT/"kernel-preview-cli.elf"
link_command=[str(archive) if p==str(CLI/"ui/libgiac.a") else
              str(entry_object) if p==str(CLI/"oracle-main.o") else
              str(executable) if p==str(CLI/"oracle.elf") else
              "-Wl,--gc-sections,-z,max-page-size=4096,-Map="+str(OUT/"kernel-preview-cli.map")
              if p.startswith("-Wl,--gc-sections,-z,max-page-size=4096,-Map=") else p
              for p in reference["commands"][-1]]
run("combined-link",link_command)
run("math-cases",[sys.executable,Path(__file__).with_name("run_dirac_cases.py"),"--elf",executable,"--output",EVIDENCE,"--label","combined"])
math=json.loads((EVIDENCE/"combined.json").read_text())
assert math["passed"]==math["total"]==26
recovery=run("transactions-run",["qemu-sh4eb",executable],input=b":transactions\n",timeout=180)
rows=[json.loads(p) for p in recovery.stdout.decode().splitlines()]
assert rows[-1]==dict(complete=True)
assert digest(ORIGINAL)==original_sha
binding=dict(passed=True,archive=str(archive),archive_sha256=digest(archive),
             elf=str(executable),elf_sha256=digest(executable),
             original_archive_sha256=original_sha,original_unchanged=True,
             source_sha256={n:digest(SOURCE/n) for n in ("ksym2poly.cc","kintgab.cc")},
             changed_members=changed,original_member_sha256=old_hashes,candidate_member_sha256=new_hashes,
             units=39,registered_commands=709,physical_arena_bytes=32768,tracked_limit_bytes=24576,
             math_passed=math["passed"],math_total=math["total"],recovery=rows,commands=commands)
(EVIDENCE/"combined-build.json").write_text(json.dumps(binding,indent=2)+"\n")
print(json.dumps({k:binding[k] for k in ("passed","archive","archive_sha256","elf_sha256","source_sha256","recovery")}),flush=True)
