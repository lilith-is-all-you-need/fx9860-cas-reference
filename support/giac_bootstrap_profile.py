"""Prepare or test the isolated Giac startup profile with the pinned SH SDK."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ARENA_BYTES = 32 * 1024


def replace_once(text, original, replacement):
    if text.count(original) != 1:
        raise ValueError(f'Unexpected prepared runtime near {original!r}')
    return text.replace(original, replacement)


def runtime_fde_object(runtime):
    manifest = runtime / 'runtime-manifest.json'
    if not manifest.is_file():
        return None
    info = json.loads(manifest.read_text()).get('heapless_fde')
    if not info:
        return None
    obj = runtime / info['object']
    if hashlib.sha256(obj.read_bytes()).hexdigest() != info['sha256']:
        raise ValueError(f'FDE object does not match the prepared runtime: {obj}')
    return obj


def integrate(start, linker, arena_bytes=APPLICATION_ARENA_BYTES):
    if not 512 <= arena_bytes <= APPLICATION_ARENA_BYTES or arena_bytes % 4:
        raise ValueError('The arena size must align to four bytes and fit the 32 KiB budget')
    start = replace_once(start, '''extern void khicas_unwind_register(void);
extern void khicas_unwind_unregister(void);''', '#include "giac_bootstrap.h"')
    start = replace_once(start, '''/* Constructor and destructor arrays */
extern void (*bctors)(void), (*ectors)(void);
extern void (*bdtors)(void), (*edtors)(void);

''', '')
    start = replace_once(start, '''/* callarray(): Call an array of functions (constructors or destructors)
   @f  First element of array
   @l  First element outside of the array */
static void callarray(void (**f)(void), void (**l)(void))
{
	while(f < l) (*(*f++))();
}

''', '')
    start = replace_once(start, '\tkinit();\n\tkhicas_unwind_register();', f'''\tkinit();
\tint startup_status = khicas_bootstrap_start({arena_bytes}u);
\tif(startup_status) {{
\t\tkquit();
\t\treturn startup_status;
\t}}''')
    start = replace_once(start, '\t\tcallarray(&bctors, &ectors);\n', '')
    start = replace_once(start, '''\telse {
\t\tcallarray(&bdtors, &edtors);
\t}
''', '')
    start = replace_once(start, '\tkhicas_unwind_unregister();\n\tkquit();',
                         '\tkquit();\n\tkhicas_bootstrap_stop();')
    linker = replace_once(linker, '''\t\t_bctors = . ;
\t\tKEEP(*(.ctors .ctors.*))
\t\t_ectors = . ;''', '''        _khicas_eh_ctors_begin = .;
        KEEP(*libstdc++.a:eh_alloc.o(.ctors .ctors.*))
        _khicas_eh_ctors_end = .;
        ASSERT(_khicas_eh_ctors_end - _khicas_eh_ctors_begin == 4,
               "Expected one EH pool constructor");

        _bctors = .;
        KEEP(*(SORT_BY_INIT_PRIORITY(.ctors.*)))
        KEEP(*(.ctors))
        _ectors = .;''')
    linker = replace_once(linker, '\t\tKEEP(*(.dtors .dtors.*))',
                         '\t\tKEEP(*(.dtors .dtors.* .preinit_array .preinit_array.*\n'
                         '\t\t       .init_array .init_array.* .fini_array .fini_array.*))')
    linker = replace_once(linker, '\t\t_edtors = . ;',
                         '\t\t_edtors = . ;\n'
                         '\t\tASSERT(_bdtors == _edtors, "Untracked constructor or destructor section");')
    return start, linker


def prepare(args):
    start, linker = integrate((args.runtime / 'gint_start.c').read_text(),
                              (args.runtime / 'fx9860giii_cas.ld').read_text(),
                              args.arena_bytes)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'gint_start.c').write_text(start)
    (args.output / 'fx9860giii_cas.ld').write_text(linker)
    for name in ('kernel.h', 'giac_unwind.c', 'unwind-dw2-fde.h'):
        shutil.copy2(args.runtime / name, args.output / name)
    fde = runtime_fde_object(args.runtime)
    if fde:
        shutil.copy2(fde, args.output / fde.name)
    manifest = json.loads((args.runtime / 'runtime-manifest.json').read_text())
    manifest.update(bootstrap_arena_bytes=args.arena_bytes,
                    bootstrap_source=str(ROOT / 'src/giac_bootstrap.cc'),
                    status='prepared experimental startup; target release gates still apply')
    (args.output / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(args.output)


def build_superh(args, executable_name, entry, objects, fault_injection=False):
    args.output.mkdir(parents=True, exist_ok=False)
    arena = args.output / 'arena.o'
    executable = args.output / executable_name
    linker = args.output / 'sh_bootstrap.ld'
    shutil.copy2(ROOT / 'tests/sh_bootstrap.ld', linker)
    compiler = args.compiler.resolve()
    flags = ['-m4-nofpu', '-DFX9860G', '-Os', '-g', '-fno-builtin',
             '-ffunction-sections', '-fdata-sections']
    cc = compiler.with_name('sh-elf-gcc')
    compile_arena = [cc, *flags, '-std=gnu11',
                     '-c', args.gint / 'src/kmalloc/arena_gint.c', '-o', arena]
    commands = [('arena', compile_arena)]
    plot_replay = getattr(args, 'plot', False)
    if plot_replay:
        gint_src = args.gint / 'src'
        render_sources = (ROOT / 'src/plot_view.c', ROOT / 'src/main.c',
                          ROOT / 'src/ui.c', gint_src / 'keysc/keycodes.c',
                          gint_src / 'render/dline.c', gint_src / 'render/dwindow.c')
        render_sources += tuple(gint_src / 'render-fx' / name for name in
                                ('dclear.c', 'dpixel.c', 'dgetpixel.c', 'drect.c',
                                 'gint_dline.c', 'masks.c'))
        for source in render_sources:
            obj = args.output / f'{source.stem}.o'
            profile = ['-DKHICAS_UI_CAS=1', '-DKHICAS_UI_PLOTS=1']
            if getattr(args, 'legacy', False):
                profile.append('-DKHICAS_GIAC_LEGACY=1')
            if source.name == 'main.c':
                profile.append('-Dmain=khicas_ui_main')
            commands.append((source.stem, [cc, *flags, *profile, '-std=gnu11', '-I', ROOT / 'src',
                                           '-c', source, '-o', obj]))
            objects.append(obj)
    elif not fault_injection and getattr(args, 'cli_object', None):
        objects = [args.cli_object, *objects]
    elif not fault_injection:
        cli = args.output / 'cas-cli.o'
        commands.append(('cli', [cc, *flags, '-std=gnu11', '-Dmain=khicas_cli_main',
                                 '-I', ROOT / 'src', '-c', ROOT / 'tests/cas_cli.c', '-o', cli]))
        objects = [cli, *objects]
    cxx_flags = [*flags, '-std=gnu++11', '-Wall', '-Wextra', '-Werror',
                 '-fexceptions', '-funwind-tables', '-I', ROOT / 'src']
    if fault_injection:
        cxx_flags.append('-DKHICAS_BOOTSTRAP_TEST')
    if plot_replay:
        cxx_flags += ['-DKHICAS_UI_PLOTS=1', '-DKHICAS_SH_PLOT_REPLAY=1']
    if getattr(args, 'legacy', False):
        cxx_flags.append('-DKHICAS_GIAC_LEGACY=1')
    test_objects = []
    for source in (ROOT / 'src/giac_bootstrap.cc', ROOT / 'tests/sh_giac_runtime.cc', entry):
        obj = args.output / f'{source.stem}.o'
        commands.append((source.stem, [compiler, *cxx_flags, '-c', source, '-o', obj]))
        test_objects.append(obj)
    # GCC's parallel LTO build runs through make. Keep source and include
    # paths (which may contain apostrophes) out of that command line.
    link = [compiler, '-m4-nofpu', '-Oz' if args.lto else '-Os', '-nostdlib', '-T', linker,
            f'-Wl,--gc-sections,-z,max-page-size=4096,-Map={args.output / "link.map"}',
            *test_objects, *objects, *args.object, args.unwind]
    fde = runtime_fde_object(args.unwind.parent)
    if fde:
        link.append(fde)
    link += [arena, '-Wl,--start-group',
            args.giac, args.tommath, args.stdlib, '-lc', '-lopenlibm', '-lgcc',
            '-Wl,--end-group', '-o', executable]
    if args.lto:
        link[1:1] = ['-flto=auto', '-fno-fat-lto-objects', '-fno-strict-aliasing',
                     '-Wl,-u,_vsprintf,-u,_fputs,-u,_strncmp,-u,_printf,-u,_strstr,-u,_strcpy,-u,_strspn']
    if args.compact_core:
        link.insert(1, '-fno-ipa-cp')
    commands.append(('link', link))
    for name, command in commands:
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        (args.output / f'{name}.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{name} failed, see {args.output / f"{name}.log"}\n{result.stderr}')
    (args.output / 'build.json').write_text(
        json.dumps({name: list(map(str, command)) for name, command in commands}, indent=2) + '\n')
    return executable


def math(args):
    name = 'sh-giac-plot' if args.plot else 'sh-giac-cli'
    entry = 'sh_giac_plot.cc' if args.plot else 'sh_giac_cli.cc'
    executable = build_superh(args, name + '.elf', ROOT / 'tests' / entry, [args.bridge])
    print(executable)


def probe(args):
    qemu = shutil.which('qemu-sh4eb')
    if not qemu:
        raise RuntimeError('qemu-sh4eb is required')
    executable = build_superh(args, 'sh-bootstrap.elf', ROOT / 'tests/sh_bootstrap.cc',
                              [args.entry], fault_injection=True)

    def run(fail_at=0, dtor_capacity=0, disable_eh=False):
        result = subprocess.run([qemu, executable],
                                input=f'{fail_at}\n{dtor_capacity}\n{int(disable_eh)}\n',
                                capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError(f'QEMU failed at allocation {fail_at}, destructor capacity '
                               f'{dtor_capacity}, disabled EH {disable_eh}: '
                               f'{result.returncode} {result.stderr}')
        columns = ['status', 'attempts', 'failure_at', 'registrations', 'peak_arena_bytes']
        return dict(zip(columns, map(int, result.stdout.split()), strict=True))

    baseline = run()
    if baseline['status'] or baseline['failure_at'] or baseline['registrations'] < 2:
        raise RuntimeError(f'Expected full Giac constructors to succeed: {baseline}')
    failures = []
    for index in range(1, baseline['attempts'] + 1):
        result = run(index)
        if result['status'] != 6 or result['failure_at'] != index:
            raise RuntimeError(f'Expected clean startup OOM at allocation {index}: {result}')
        failures.append(result)
    if run(baseline['attempts'] + 1) != baseline:
        raise RuntimeError('An allocation fault outside startup changed the baseline')
    destructor_failures = []
    for capacity in sorted({1, baseline['registrations'] - 1}):
        result = run(dtor_capacity=capacity)
        if result['status'] != 6 or result['registrations'] != capacity:
            raise RuntimeError(f'Expected clean registration failure at capacity {capacity}: {result}')
        destructor_failures.append(dict(capacity=capacity, **result))
    disabled_eh = run(disable_eh=True)
    if disabled_eh['status'] != 2 or disabled_eh['registrations']:
        raise RuntimeError(f'Expected rejection before Giac when EH is disabled: {disabled_eh}')
    report = {'baseline': baseline, 'allocation_failures': failures,
              'destructor_capacity_failures': destructor_failures,
              'disabled_eh': disabled_eh,
              'arena_bytes': APPLICATION_ARENA_BYTES,
              'scope': 'SuperH userspace, synthetic kernel allocations, no calculator hardware'}
    (args.output / 'startup-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(failures)} allocation failures and {len(destructor_failures)} '
          f'registration failures recovered. Peak application arena use '
          f'{baseline["peak_arena_bytes"]} bytes with {baseline["registrations"]} registrations.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    preparation = commands.add_parser('prepare')
    preparation.add_argument('--runtime', type=Path, required=True)
    preparation.add_argument('--output', type=Path, required=True)
    preparation.add_argument('--arena-bytes', type=int, required=True)
    preparation.set_defaults(action=prepare)
    test = commands.add_parser('probe')
    test.add_argument('--entry', type=Path, required=True)
    test.set_defaults(action=probe)
    mathematics = commands.add_parser('math')
    mathematics.add_argument('--bridge', type=Path, required=True)
    mathematics.add_argument('--plot', action='store_true',
                             help='Replay plots with the real C ABI and gint VRAM routines')
    mathematics.add_argument('--legacy', action='store_true',
                             help='Use the retained legacy kernel plot coverage')
    mathematics.set_defaults(action=math)
    for command in (test, mathematics):
        for option in ('giac', 'tommath', 'stdlib', 'unwind', 'gint', 'output'):
            command.add_argument(f'--{option}', type=Path, required=True)
        command.add_argument('--object', type=Path, action='append', default=[],
                             help='Additional target object, ordered before the kernel archive')
        command.add_argument('--cli-object', type=Path,
                             help='Use a precompiled khicas_cli_main test entry instead of cas_cli.c')
        command.add_argument('--lto', action='store_true')
        command.add_argument('--compact-core', action='store_true',
                             help='Match the compact core IPA optimization setting at link time')
        command.add_argument('--compiler', type=Path, default=Path.home() / '.local/bin/sh-elf-g++')
    args = parser.parse_args()
    args.action(args)


if __name__ == '__main__':
    main()
