"""Relink only the small directional recovery test with the new isolated core."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--baseline",action="store_true")
    args=parser.parse_args()
    out=args.build.resolve()
    evidence=out/"evidence"
    base=Path("/root/khicas-work/symbol-transaction-20261114/clean-combined-static-cli")
    reference=json.loads((base/"oracle-build.json").read_text())
    commands=[]
    env=dict(os.environ,LD_LIBRARY_PATH="/opt/khicas-host/lib/x86_64-linux-gnu")
    def run(label,command,timeout=600):
        commands.append(dict(label=label,command=command))
        print(label,flush=True)
        result=subprocess.run(command,capture_output=True,env=env,timeout=timeout)
        (evidence/(label+".stdout")).write_bytes(result.stdout)
        (evidence/(label+".stderr")).write_bytes(result.stderr)
        assert result.returncode==0,(label,result.returncode,result.stderr.decode(errors="replace")[-2000:])
        return result.stdout
    source=Path(__file__).with_name("dirac_transactions.cc")
    label="baseline-transactions" if args.baseline else "dirac-transactions"
    obj=out/(label+".o")
    command=list(reference["commands"][0])
    command[command.index("-c")+1]=str(source)
    command[command.index("-o")+1]=str(obj)
    if args.baseline: command.insert(1,"-DBASELINE_RECOVERY")
    run(label+"-compile",command)
    command=json.loads((evidence/"build.json").read_text())["commands"][-1]["command"]
    executable=out/(label+".elf")
    command=[str(obj) if p==str(base/"oracle-main.o") else
             str(executable) if p==str(out/"dirac-preview-cli.elf") else
             "-Wl,--gc-sections,-z,max-page-size=4096,-Map="+str(out/(label+".map"))
             if p.startswith("-Wl,--gc-sections,-z,max-page-size=4096,-Map=") else p for p in command]
    if args.baseline:
        command=[str(base/"ui/libgiac.a") if p==str(out/"libgiac-dirac-preview.a") else p for p in command]
    run(label+"-link",command)
    test_command=["qemu-sh4eb",str(executable)]
    result=subprocess.run(test_command,capture_output=True,env=env,timeout=180)
    (evidence/(label+"-run.stdout")).write_bytes(result.stdout)
    (evidence/(label+"-run.stderr")).write_bytes(result.stderr)
    commands.append(dict(label=label+"-run",command=test_command))
    rows=[json.loads(line) for line in result.stdout.decode().splitlines()]
    passed=result.returncode==0 and bool(rows) and rows[-1]==dict(complete=True)
    report=dict(passed=passed,baseline=args.baseline,exit_code=result.returncode,
                stderr=result.stderr.decode(errors="replace"),
                physical_arena_bytes=32768,tracked_limit_bytes=24576,
                elf_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                cases=rows,commands=commands)
    (evidence/(label+".json")).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"passed":passed,"baseline":args.baseline,"cases":rows,"stderr":report["stderr"]}),flush=True)
    if not passed: raise SystemExit(1)


if __name__=="__main__": main()
