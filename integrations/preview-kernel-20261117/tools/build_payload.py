"""Build the complete mapped CAS payload with the preserved Linux toolchain.

Default execution freezes a plan only. --run compiles the small mapped-runtime
replacements and performs one serial LTO link against the unchanged full core.
Run inside the task VM; Windows GCC cannot read the archived zlib LTO objects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


FROZEN = Path('/root/khicas-work/symbol-transaction-ui-size-20261114')
FULL_CORE = Path('/root/khicas-work/symbol-transaction-20261114/combined-clean-static/libgiac.a')
FULL_CORE_SHA = '1b127e8f3e44cdb7452ea5d8bad8e792d1a6ea4bfa6962a14910d2598028e098'
STARTUP_HEADERS = Path('/root/khicas-work/formal-leaf-ui-size-20261114/startup')
DEFAULT_OUTPUT = Path('/root/khicas-work/preview-kernel-20261117/payload-build')
ROOT = Path(__file__).resolve().parents[3]
PAYLOAD = ROOT / 'integrations/preview-kernel-20261117/payload'
SOURCE_NAMES = ('start.c', 'main.c', 'binding.c', 'atomic.c', 'map_api.h', 'tlbh.S', 'syscalls.S')
HEADERS = {
    'ui.h': None,
    'math_layout.h': None,
    'plot_view.h': 'e16cbc5fe12de054d978210a28789b790b5f42f8c89c0dba0df4eda2f8c5e768',
    'giac_port.h': '59725a8593822c4070a9b666c22a1f20e89561c14f44c9a78429f84bbb8f22ee',
}
NO_FORMAL = ('khicas_bind_external_formal_twoarg', 'formal_twoarg_leaf',
             'Formal derivative leaf unavailable')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n')


def checked_input(path: Path, expected: str | None = None) -> str:
    if not path.is_file():
        raise ValueError(f'Required input is missing: {path}')
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError(f'Frozen input hash changed: {path}')
    return actual


def run(command, name: str, output: Path, records: list) -> str:
    command = list(map(str, command))
    began = time.monotonic()
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    (output / (name + '.log')).write_text(result.stdout)
    records.append({'command': command, 'exit_code': result.returncode,
                    'seconds': time.monotonic() - began, 'log': name + '.log'})
    save(output / 'commands.json', records)
    if result.returncode:
        raise RuntimeError(f'{name} failed; see {output / (name + ".log")}\n'
                           + result.stdout[-4000:])
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=PAYLOAD)
    parser.add_argument('--project-src', type=Path, default=ROOT / 'src')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--compiler', type=Path, default=Path('/root/.local/bin/sh-elf-g++'))
    parser.add_argument('--core', type=Path, default=FULL_CORE)
    parser.add_argument('--core-sha', default=FULL_CORE_SHA)
    parser.add_argument('--payload-base', type=lambda s: int(s, 0), default=0x00300000,
                        help='Virtual address of the 512-byte external-file header')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--compile-only', action='store_true',
                      help='Compile runtime replacements without the final LTO link')
    args = parser.parse_args()
    source, project_src = args.source.resolve(), args.project_src.resolve()
    output = args.output.resolve()
    compiler = args.compiler.absolute()
    core = args.core.resolve()
    tool = lambda name: compiler.with_name('sh-elf-' + name)
    if args.payload_base & 4095:
        parser.error('--payload-base must be page aligned')
    if not 0x00300000 <= args.payload_base < 0x08000000:
        parser.error('External payload must use a valid P0 virtual range')
    version = subprocess.check_output([compiler, '-dumpfullversion'], text=True).strip()
    target = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
    if (version, target) != ('14.1.0', 'sh3eb-elf'):
        raise ValueError('Use the preserved GCC 14.1.0 sh3eb-elf compiler')

    input_sha = {str(compiler): checked_input(compiler),
                 str(core): checked_input(core, args.core_sha),
                 str(Path(__file__).resolve()): checked_input(Path(__file__).resolve())}
    for name in SOURCE_NAMES:
        path = source / name
        input_sha[str(path)] = checked_input(path)
    for name, expected in HEADERS.items():
        path = project_src / name
        input_sha[str(path)] = checked_input(path, expected)
    for name in ('ui.c', 'math_layout.c'):
        path = project_src / name
        input_sha[str(path)] = checked_input(path)
    for name in ('kernel.h', 'giac_bootstrap.h'):
        path = STARTUP_HEADERS / name
        input_sha[str(path)] = checked_input(path)

    frozen_report = json.loads((FROZEN / 'preparation.json').read_text())
    original = json.loads((FROZEN / 'link.json').read_text())['command']
    for arg in original:
        path = Path(arg)
        if path.suffix not in ('.o', '.a', '.ld') or not path.is_file():
            continue
        expected = frozen_report['input_sha256'].get(str(path))
        if isinstance(expected, dict):
            expected = expected['sha256']
        if expected is None:
            raise ValueError(f'Frozen manifest does not identify {path}')
        input_sha[str(path)] = checked_input(path, expected)

    output.mkdir(parents=True, exist_ok=True)
    for previous_result in ('build-result.json', 'compile-result.json'):
        previous = output / previous_result
        if previous.is_file():
            previous.unlink()
    include = output / 'include'
    objects = output / 'objects'
    include.mkdir(exist_ok=True)
    objects.mkdir(exist_ok=True)
    for name in ('kernel.h', 'giac_bootstrap.h'):
        shutil.copy2(STARTUP_HEADERS / name, include / name)

    entry = args.payload_base + 512
    linker_text = (FROZEN / 'inputs/08-measurement-only.ld').read_text()
    if linker_text.count('o = 0x00300200, l = 3400k') != 1:
        raise ValueError('Unexpected frozen linker ROM declaration')
    linker_text = linker_text.replace('0x00300200', f'0x{entry:08x}')
    linker_text = linker_text.replace('0x00300000', f'0x{args.payload_base:08x}')
    linker = output / 'mapped-payload.ld'
    linker.write_text(linker_text)
    input_sha[str(linker)] = sha(linker)

    plan = {'status': 'prepared', 'compiler_version': version, 'target': target,
            'source_sha256': input_sha, 'payload_base': args.payload_base,
            'entry_address': entry, 'physical_arena_bytes': 32768,
            'tracker_limit_bytes': 24576, 'full_core_sha256': args.core_sha,
            'gint_removed_members': ['start.c.obj', 'tlbh.S.obj', 'syscalls.S.obj', 'atomic.c.obj'],
            'math_source_changes': args.core_sha != FULL_CORE_SHA,
            'heavy_links_requested': int(args.run)}
    save(output / 'build-plan.json', plan)
    if not args.run and not args.compile_only:
        print(json.dumps(plan, indent=2))
        return

    records = []
    cflags = ['-m4-nofpu', '-mb', '-DFX9860G', '-std=gnu11', '-Os', '-g',
              '-fno-builtin', '-ffunction-sections', '-fdata-sections',
              '-Wall', '-Wextra', '-Werror', '-DKHICAS_UI_CAS=1',
              '-DKHICAS_UI_PLOTS=1', '-DKHICAS_GIAC_LEGACY=1',
              '-DKHICAS_UI_2D=1', '-I' + str(source),
              '-I' + str(include), '-I' + str(project_src)]
    for name in ('start', 'main', 'binding'):
        flags = list(cflags)
        if name == 'binding':
            flags[0] = '-m4a-nofpu'
        run([tool('gcc'), *flags, '-c', source / (name + '.c'),
             '-o', objects / (name + '.o')], name + '-compile', output, records)
    for name in ('ui', 'math_layout'):
        run([tool('gcc'), *cflags, '-c', project_src / (name + '.c'),
             '-o', objects / (name + '.o')], name + '-compile', output, records)
    run([tool('gcc'), *cflags, '-c', source / 'atomic.c',
         '-o', objects / 'atomic.c.obj'], 'atomic-compile', output, records)
    for name in ('tlbh', 'syscalls'):
        run([tool('gcc'), '-m4a-nofpu', '-mb', '-DFX9860G', '-I' + str(source),
             '-I' + str(include), '-x', 'assembler-with-cpp', '-c',
             source / (name + '.S'), '-o', objects / (name + '.S.obj')],
            name + '-assemble', output, records)

    gint = output / 'libgint-fx.a'
    shutil.copy2(FROZEN / 'inputs/16-libgint-fx.a', gint)
    run([tool('gcc-ar'), 'd', gint, 'start.c.obj', 'tlbh.S.obj', 'syscalls.S.obj', 'atomic.c.obj'],
        'gint-remove-originals', output, records)
    run([tool('gcc-ar'), 'rcs', gint, objects / 'tlbh.S.obj', objects / 'syscalls.S.obj',
         objects / 'atomic.c.obj'],
        'gint-install-replacements', output, records)
    members = run([tool('ar'), 't', gint], 'gint-members', output, records).splitlines()
    if 'start.c.obj' in members or any(members.count(n + '.S.obj') != 1
                                      for n in ('tlbh', 'syscalls')) or members.count('atomic.c.obj') != 1:
        raise ValueError('The mapped gint archive contains wrong replacement members')
    if args.compile_only:
        save(output / 'compile-result.json', {
            **plan, 'status': 'runtime replacements compiled; no final link',
            'commands': records,
            'object_sha256': {str(p): sha(p) for p in (gint, *objects.iterdir())}})
        print('Runtime replacements compiled; no final LTO link requested')
        return

    replacement = {
        str(FROZEN / 'inputs/00-main.o'): str(objects / 'main.o'),
        str(FROZEN / 'inputs/01-ui.o'): str(objects / 'ui.o'),
        str(FROZEN / 'inputs/08-measurement-only.ld'): str(linker),
        str(FROZEN / 'inputs/09-gint_start32.o'): str(objects / 'start.o'),
        str(FROZEN / 'inputs/13-libgiac.a'): str(core),
        str(FROZEN / 'inputs/16-libgint-fx.a'): str(gint),
        str(FROZEN / 'ui.elf'): str(output / 'payload.elf'),
    }
    command = []
    for arg in original:
        if arg.startswith('-Wl,-u,__Unwind_Resume,'):
            continue
        if arg.startswith('-Wl,--gc-sections,-Map='):
            arg = '-Wl,--gc-sections,-Map=' + str(output / 'payload.map')
        command.append(replacement.get(arg, arg))
    command[0] = str(compiler)
    command.insert(command.index(str(objects / 'main.o')) + 1, str(objects / 'binding.o'))
    command.insert(command.index(str(objects / 'ui.o')) + 1, str(objects / 'math_layout.o'))
    for path, digest in input_sha.items():
        if sha(Path(path)) != digest:
            raise ValueError(f'Input changed before final link: {path}')
    run(command, 'payload-link', output, records)
    elf = output / 'payload.elf'
    undefined = run([tool('nm'), '-u', elf], 'payload-undefined', output, records)
    if undefined.strip():
        raise ValueError('The complete payload contains undefined symbols')
    run([tool('nm'), '-n', elf], 'payload-symbols', output, records)
    run([tool('objdump'), '-h', elf], 'payload-load-sections', output, records)
    run([tool('readelf'), '-h', '-l', elf], 'payload-elf-headers', output, records)
    run([tool('size'), '-A', elf], 'payload-sections', output, records)
    run([tool('objcopy'), '-O', 'binary', '-R', '.bss', '-R', '.gint.bss',
         elf, output / 'payload.bin'], 'payload-objcopy', output, records)
    data = elf.read_bytes()
    forbidden = [n for n in NO_FORMAL if n.encode() in data]
    if forbidden:
        raise ValueError('Payload still contains the removed formal module path: '
                         + ', '.join(forbidden))
    for path, digest in input_sha.items():
        if sha(Path(path)) != digest:
            raise ValueError(f'Input changed during final link: {path}')
    binary = output / 'payload.bin'
    final = {**plan, 'status': 'linked and statically checked',
             'undefined_symbols': [], 'removed_formal_module_path': True,
             'payload_bytes': binary.stat().st_size,
             'file_with_512_byte_header': binary.stat().st_size + 512,
             'mapped_pages': (binary.stat().st_size + 512 + 4095) // 4096,
             'artifact_sha256': {str(p): sha(p) for p in
                                 (elf, binary, linker, gint, *objects.iterdir())},
             'commands': records, 'hardware_verified': False}
    save(output / 'build-result.json', final)
    print(json.dumps({k: v for k, v in final.items()
                      if k not in ('source_sha256', 'commands', 'artifact_sha256')}, indent=2))


if __name__ == '__main__':
    main()
