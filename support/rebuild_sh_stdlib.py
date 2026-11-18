"""Rebuild the configured SuperH C++ runtime and verify it under QEMU.

Run in WSL. The SDK and the original GCC build remain untouched. Link with
the archive this tool reports to use the exception-enabled runtime.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from giac_bootstrap_profile import runtime_fde_object


BUILD_SUBDIR = Path('build/sh3eb-elf/m4-nofpu/libstdc++-v3')
EXCEPTION_FLAGS = '-fexceptions -funwind-tables'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcc-workspace', type=Path, required=True,
                        help='Directory containing gcc-14.1.0 and the configured build')
    parser.add_argument('--runtime', type=Path, required=True,
                        help='Directory prepared by prepare_target_runtime.py')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for the isolated runtime build')
    parser.add_argument('--compiler', type=Path,
                        default=Path('/root/.local/bin/sh-elf-g++'))
    parser.add_argument('--jobs', type=int, default=12)
    args = parser.parse_args()
    original = args.gcc_workspace.resolve() / BUILD_SUBDIR
    source = args.gcc_workspace.resolve() / 'gcc-14.1.0'
    output = args.output.resolve()
    runtime = args.runtime.resolve()
    compiler = args.compiler.absolute()
    if output.is_relative_to(args.gcc_workspace.resolve()):
        parser.error('--output must be outside the original GCC workspace')
    if output.exists():
        parser.error('--output must be a new directory')
    if args.jobs < 1:
        parser.error('--jobs must be at least one')
    if (source / 'gcc/BASE-VER').read_text().strip() != '14.1.0':
        parser.error('GCC source version 14.1.0 is required for this configured profile')
    if subprocess.check_output([compiler, '-dumpmachine'], text=True).strip() != 'sh3eb-elf':
        parser.error('--compiler must target big-endian SuperH (sh3eb-elf)')
    if subprocess.check_output([compiler, '-dumpfullversion'], text=True).strip() != '14.1.0':
        parser.error('--compiler must match GCC source version 14.1.0')

    env = dict(os.environ, PATH=f'{compiler.parent}:{os.environ["PATH"]}')
    qemu = shutil.which('qemu-sh4eb', path=env['PATH'])
    if not qemu:
        parser.error('qemu-sh4eb is required to run the target exception test')
    original_archive = original / 'src/.libs/libstdc++.a'
    original_hash = digest(original_archive)
    target = output / BUILD_SUBDIR
    output.mkdir(parents=True)
    (output / 'gcc-14.1.0').symlink_to(source, target_is_directory=True)
    shutil.copytree(original, target, symlinks=True)
    replaced = 0
    for makefile in sorted(target.rglob('Makefile')):
        if makefile.is_symlink():
            raise ValueError(f'Unexpected symlink at {makefile}')
        contents = makefile.read_text().replace(str(original), str(target))
        contents, count = re.subn(
            r'^EXTRA_CXX_FLAGS\s*=.*-fno-exceptions.*$',
            f'EXTRA_CXX_FLAGS = {EXCEPTION_FLAGS}', contents, flags=re.M)
        makefile.write_text(contents)
        replaced += count
    if not replaced:
        raise ValueError('No configured -fno-exceptions flags found in the copied build')

    def log_run(command, logfile, cwd=target):
        with (output / logfile).open('w') as log:
            subprocess.run(command, cwd=cwd, env=env, check=True,
                           stdout=log, stderr=subprocess.STDOUT)

    log_run(['make', 'clean'], 'clean.log')
    log_run(['make', f'-j{args.jobs}', f'CXXFLAGS=-g -Os {EXCEPTION_FLAGS}'], 'build.log')
    if digest(original_archive) != original_hash:
        raise RuntimeError('The original configured GCC archive changed')
    archive = target / 'src/.libs/libstdc++.a'
    registered = output / 'giac_unwind.o'
    command = [compiler, '-m4-nofpu', '-Os', '-ffunction-sections',
               '-fdata-sections', '-x', 'c', '-c', runtime / 'giac_unwind.c',
               '-o', registered]
    log_run(command, 'unwind-compile.log')
    tests = Path(__file__).resolve().parents[1] / 'tests'
    exe = output / 'sh-unwind-probe.elf'
    fde = runtime_fde_object(runtime)
    link = [compiler, '-m4-nofpu', '-std=gnu++11', '-Os', '-fno-builtin',
            '-ffunction-sections', '-fdata-sections', '-funwind-tables',
            '-nostdlib', '-T', tests / 'sh_unwind_probe.ld',
            '-Wl,--gc-sections,-z,max-page-size=4096', tests / 'sh_unwind_probe.cc',
            registered, *([fde] if fde else []), '-Wl,--start-group', archive,
            '-lc', '-lopenlibm', '-lgcc',
            '-Wl,--end-group', '-o', exe]
    log_run(link, 'unwind-link.log')
    log_run([qemu, exe], 'unwind-run.log')
    report = {'archive': str(archive), 'archive_sha256': digest(archive),
              'original_archive_sha256': original_hash,
              'flags': EXCEPTION_FLAGS, 'configuration_files_changed': replaced,
              'probe_output': (output / 'unwind-run.log').read_text().strip()}
    (output / 'unwind-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
