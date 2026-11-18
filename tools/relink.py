"""Run a recorded payload build with the matching project source and core."""
import argparse
from pathlib import Path
import subprocess
import sys

WORK = Path("/root/khicas-work")
VARIANTS = {
    "699": ("mapped-integration-20261116", "mapped-cas-20261116"),
    "701": ("preview-kernel-20261117", "preview-kernel-20261117"),
}
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="Compile and perform the LTO link")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Use a new output directory")
    snapshot, project = VARIANTS[args.variant]
    script = WORK / snapshot / "staging/project/integrations" / project / "tools/build_payload.py"
    if not script.is_file():
        parser.error("Restore giac-source-and-relink-inputs.tar.gz under /root/khicas-work in an isolated Linux build environment")
    command = [sys.executable, str(script), "--output", str(output)]
    if args.variant == "701":
        command += ["--core", str(WORK / "preview-kernel-20261117/kernel/build-v3/libgiac-kernel-preview.a"),
                    "--core-sha", "c9e9a3afc0b40c80239b57777b396fcc1d3c0b3a5286a6708e525d2d2ab822cc"]
    if args.run:
        command.append("--run")
    return subprocess.call(command)
if __name__ == "__main__":
    raise SystemExit(main())
