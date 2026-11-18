"""Compile one isolated SH unit and relink an isolated copy of the proven CLI."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

BASE = Path("/root/khicas-work/symbol-transaction-20261114")
SOURCE = BASE / "combined-clean-source"
ARCHIVE = BASE / "combined-clean-static/libgiac.a"
CLI = BASE / "clean-combined-static-cli"
ARCHIVE_SHA = "1b127e8f3e44cdb7452ea5d8bad8e792d1a6ea4bfa6962a14910d2598028e098"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    evidence = out / "evidence"
    evidence.mkdir(exist_ok=True)
    assert digest(ARCHIVE) == ARCHIVE_SHA
    before_source = {p.name:digest(p) for p in SOURCE.iterdir() if p.is_file()}
    source_copy = out / "source"
    if source_copy.exists():
        raise SystemExit("Choose a fresh build directory")
    shutil.copytree(SOURCE, source_copy)
    prepare = Path(__file__).with_name("prepare_dirac_fix.py")
    subprocess.run([sys.executable,str(prepare),"--source",str(SOURCE / "kintgab.cc"),
                    "--output",str(source_copy)],check=True)
    env = dict(os.environ, LD_LIBRARY_PATH="/opt/khicas-host/lib/x86_64-linux-gnu")
    commands = []

    def run(name, command):
        command = list(map(str, command))
        commands.append(dict(label=name, command=command))
        print(name, flush=True)
        result = subprocess.run(command, capture_output=True, env=env, timeout=600)
        (evidence / (name + ".stdout")).write_bytes(result.stdout)
        (evidence / (name + ".stderr")).write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError((name,result.returncode,result.stderr.decode(errors="replace")[-2500:]))
        return result.stdout

    report = json.loads((BASE / "inputs/report.json").read_text())
    flags = [flag.replace("-flto=auto", "-flto=1") for flag in report["flags"]]
    flags = ["-I"+str(source_copy) if flag=="-I"+report["source"] else flag for flag in flags]
    obj = out / "kintgab.o"
    run("kintgab-compile", [report["compiler"],*flags,"-frandom-seed=0","-c",
                             source_copy/"kintgab.cc","-o",obj])
    candidate_archive = out / "libgiac-dirac-preview.a"
    shutil.copy2(ARCHIVE,candidate_archive)
    ar = "/root/.local/bin/sh-elf-gcc-ar"
    members = run("archive-members-before",[ar,"t",ARCHIVE]).decode().splitlines()
    assert len(members)==39 and len(set(members))==39
    old_hashes = {name:hashlib.sha256(subprocess.check_output([ar,"p",str(ARCHIVE),name],env=env)).hexdigest() for name in members}
    run("archive-replace",[ar,"rcs",candidate_archive,obj])
    assert run("archive-members-after",[ar,"t",candidate_archive]).decode().splitlines()==members
    new_hashes = {name:hashlib.sha256(subprocess.check_output([ar,"p",str(candidate_archive),name],env=env)).hexdigest() for name in members}
    changed = [name for name in members if old_hashes[name]!=new_hashes[name]]
    assert changed==["kintgab.o"],changed
    base_link = json.loads((CLI/"oracle-build.json").read_text())["commands"][-1]
    candidate_elf = out / "dirac-preview-cli.elf"
    candidate_map = out / "dirac-preview-cli.map"
    archive_replaced = 0
    command = []
    for word in base_link:
        if word==str(CLI/"ui/libgiac.a"):
            word=str(candidate_archive)
            archive_replaced += 1
        elif word==str(CLI/"oracle.elf"):
            word=str(candidate_elf)
        elif word.startswith("-Wl,--gc-sections,-z,max-page-size=4096,-Map="):
            word="-Wl,--gc-sections,-z,max-page-size=4096,-Map="+str(candidate_map)
        command.append(word)
    assert archive_replaced==1
    run("cli-link",command)
    after_source = {p.name:digest(p) for p in SOURCE.iterdir() if p.is_file()}
    assert before_source==after_source
    assert digest(ARCHIVE)==ARCHIVE_SHA
    binding = dict(accepted_archive=str(ARCHIVE),accepted_archive_sha256=ARCHIVE_SHA,
                   accepted_source_manifest=before_source,accepted_inputs_unchanged=True,
                   candidate_source=str(source_copy),candidate_source_sha256=digest(source_copy/"kintgab.cc"),
                   candidate_archive=str(candidate_archive),candidate_archive_sha256=digest(candidate_archive),
                   original_member_sha256=old_hashes,candidate_member_sha256=new_hashes,
                   changed_members=changed,units=39,registered_commands_unchanged=709,
                   candidate_elf=str(candidate_elf),candidate_elf_sha256=digest(candidate_elf),
                   original_cli=str(CLI/"oracle.elf"),original_cli_sha256=digest(CLI/"oracle.elf"),
                   physical_arena_bytes=32768,tracked_limit_bytes=24576,
                   commands=commands)
    (evidence/"build.json").write_text(json.dumps(binding,indent=2)+"\n")
    print(json.dumps({"candidate_elf":str(candidate_elf),"changed_members":changed,
                      "archive_sha256":binding["candidate_archive_sha256"]}),flush=True)


if __name__=="__main__":
    main()
