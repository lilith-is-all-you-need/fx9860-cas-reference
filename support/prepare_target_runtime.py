"""Prepare the guarded GIII startup, memory reservation and linker layout.

This operates on copies, retaining the SDK and compiler source hashes. The
GCC private unwind object layout is compiled from that compiler's own header,
not guessed or overlaid onto an application object.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from giac_bootstrap_profile import APPLICATION_ARENA_BYTES, ROOT, integrate

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--gint', type=Path, required=True)
p.add_argument('--gcc', type=Path, required=True)
p.add_argument('--linker', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--compiler', type=Path, default=Path.home() / '.local/bin/sh-elf-gcc')
p.add_argument('--static-ram-kib', type=int, default=13,
               help='Static RAM for the guarded GIII runtime, at most 13 KiB')
a = p.parse_args()
if not 1 <= a.static_ram_kib <= 13:
    p.error('GIII static RAM must leave the 14 KiB Fugue stack and 0x1100-byte VBR region intact')
if (a.gcc / 'gcc/BASE-VER').read_text().strip() != '14.1.0':
    p.error('The unwind object layout requires GCC 14.1.0 sources')
a.output.mkdir(parents=True, exist_ok=False)
start = (a.gint / 'src/kernel/start.c').read_text()
linker = a.linker.read_text()

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f'Expected one runtime patch location: {old!r}')
    return text.replace(old, new)


def prepare_fde_object(compiler, output):
    """Use the installed GCC fallback search without its heap-backed index."""
    def run(*command):
        return subprocess.check_output(command)

    if run(compiler, '-dumpmachine').strip() != b'sh3eb-elf' or \
            run(compiler, '-dumpfullversion').strip() != b'14.1.0':
        raise ValueError('Expected the pinned big-endian SuperH GCC 14.1.0 toolchain')
    library = Path(run(compiler, '-m4-nofpu', '-print-libgcc-file-name').decode().strip())
    member = 'unwind-dw2-fde.o'
    original = run(compiler.with_name('sh-elf-ar'), 'p', library, member)
    target = output / member
    # These allocating convenience functions dereference the returned object.
    # Keep only the caller-owned frame-info interfaces externally available.
    hidden = ('___register_frame', '___register_frame_table', '___deregister_frame')
    with tempfile.TemporaryDirectory(dir=output) as directory:
        stock = Path(directory) / member
        stock.write_bytes(original)
        changes = ['--redefine-sym', '_malloc=_khicas_unwind_malloc']
        for symbol in hidden:
            changes += ['--localize-symbol', symbol]
        run(compiler.with_name('sh-elf-objcopy'), *changes, stock, target)
    symbols = run(compiler.with_name('sh-elf-nm'), '-g', target).decode()
    exported = {line.split()[-1] for line in symbols.splitlines() if line.strip()}
    if '_malloc' in exported or not {'_khicas_unwind_malloc', '__Unwind_Find_FDE',
                                    '___register_frame_info',
                                    '___deregister_frame_info'} <= exported or set(hidden) & exported:
        raise RuntimeError('Unexpected FDE override symbols')
    return {'object': member, 'libgcc': str(library),
            'original_sha256': hashlib.sha256(original).hexdigest(),
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}


start = replace_once(start, '#include "kernel.h"', '''#include "kernel.h"
extern void khicas_unwind_register(void);
extern void khicas_unwind_unregister(void);''')
start = replace_once(start, '\thw_detect();', '''\thw_detect();
\t/* Check the hardware before preload, construction, or installing gint. */
\tif(gint[HWMPU] != HWMPU_SH7305 || gint[HWCALC] != HWCALC_G35PE2
\t   || mmu_uram_size() < 32768) {
\t\treturn 1;
\t}''')
start = replace_once(start, '\tkinit();', '\tkinit();\n\tkhicas_unwind_register();')
start = replace_once(start, '\tkquit();', '\tkhicas_unwind_unregister();\n\tkquit();')
(a.output / 'kernel.h').write_bytes((a.gint / 'src/kernel/kernel.h').read_bytes())

linker = replace_once(linker, 'o = 0x00300200, l = 500k', 'o = 0x00300200, l = 2800k')
linker = replace_once(linker, 'o = 0x08100200, l = 6k',
                      f'o = 0x08100200, l = {a.static_ram_kib}k')
# SDK's 6 KiB region also supports SH3's 8 KiB user mapping. The guarded GIII
# has 32 KiB. Its known gint layout leaves 0x3500 bytes after reserving the
# startup area, full 14 KiB Fugue stack and VBR. Limit static data to 13 KiB,
# leaving at least 256 bytes for arena metadata; no fixed OS RAM is borrowed.
# Keep the guarded entry and its gint dependencies below the conservative
# first ROM mapping range.
linker = replace_once(linker, '\t\t*(.text .text.*)', '''        _khicas_gint_start = .;
        *libgint-fx.a:*(.text .text.*)
        _khicas_gint_end = .;
\t\t*(.text .text.*)''')
linker = replace_once(linker, '\t\t*(.rodata .rodata.*)', '''\t\t*(.rodata .rodata.*)
        *(.gcc_except_table .gcc_except_table.*)''')
linker = replace_once(linker, '''\t_srom = 0x200
\t      + SIZEOF(.text) + SIZEOF(.rodata)
\t      + SIZEOF(.gint.drivers) + SIZEOF(.gint.blocks);''', '''    /* The TLB handler must cover section alignment and every ROM load
       image, including data and relocated gint code, not just their sum. */
    _khicas_rom_end = LOADADDR(.gint.mapped) + SIZEOF(.gint.mapped);
    _srom = _khicas_rom_end - _brom;''')
marker = '\t/*\n\t**  RAM sections\n\t*/'
linker = replace_once(linker, marker, '''    /* Synchronous exception unwind records, registered before C++ ctors. */
    .eh_frame ALIGN(4) : {
        _khicas_eh_begin = .;
        KEEP(*(.eh_frame))
        LONG(0)
        _khicas_eh_end = .;
    } > rom

    ASSERT(_start == 0x00300200, "Entry must follow the G1A header")
    ASSERT(_khicas_gint_end < 0x00300200 + 500k,
           "Early hardware guard dependencies exceed the first ROM range")
    ASSERT(_euram <= 0x08100000 + 32768 - 0x3800 - 0x1100 - 256,
           "Static RAM must leave room for gint's arena, VBR and Fugue stack")
    ASSERT(SIZEOF(.ilram) == 0 && SIZEOF(.xyram) == 0,
           "Stateful on-chip memory requires an explicit world-switch backup policy")
    ASSERT(_khicas_rom_end >= ADDR(.eh_frame) + SIZEOF(.eh_frame),
           "ROM mapping must cover all exception records")
    ASSERT(_khicas_rom_end >= LOADADDR(.data.4) + SIZEOF(.data.4),
           "ROM mapping must cover initialized data")

''' + marker)
linker = replace_once(linker, '\t\t/* Asynchronous unwind tables: no C++ exception handling */\n\t\t*(.eh_frame_hdr)\n\t\t*(.eh_frame)',
                      '\t\t/* Frame information is registered directly; no binary-search header. */\n\t\t*(.eh_frame_hdr)')
start, linker = integrate(start, linker)
(a.output / 'gint_start.c').write_text(start)
(a.output / 'fx9860giii_cas.ld').write_text(linker)

unwind = '''/* GCC 14.1.0 SH registration layout comes from its own private header. */
#include <stddef.h>
#include <unwind.h>
#include "unwind-dw2-fde.h"
extern const unsigned char khicas_eh_begin[];
static struct object registered_frames;
void khicas_unwind_register(void) {
    __register_frame_info(khicas_eh_begin, &registered_frames);
}
void khicas_unwind_unregister(void) {
    __deregister_frame_info(khicas_eh_begin);
}
/* Linked only from the private libgcc FDE object. Its original linear
   lookup handles a missing sort buffer without consuming the CAS arena. */
void *khicas_unwind_malloc(size_t bytes) {
    (void)bytes;
    return NULL;
}
'''
(a.output / 'giac_unwind.c').write_text(unwind)
header = a.gcc / 'libgcc/unwind-dw2-fde.h'
(a.output / header.name).write_bytes(header.read_bytes())
bootstrap = ROOT / 'src/giac_bootstrap.cc'
sources = [a.gint / 'src/kernel/start.c', a.linker, header, bootstrap, bootstrap.with_suffix('.h')]
fde = prepare_fde_object(a.compiler, a.output)
(a.output / 'runtime-manifest.json').write_text(json.dumps({
    'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    'rom_limit_bytes': 2800 * 1024, 'static_ram_limit_bytes': a.static_ram_kib * 1024,
    'rom_mapping': 'full load image through .gint.mapped, including alignment gaps',
    'user_ram_bytes': 32768, 'stack_reserve_bytes': 0x3800,
    'vbr_reserve_bytes': 0x1100, 'startup_reserve_bytes': 512,
    'minimum_remaining_arena_bytes': 32768 - 0x3800 - 0x1100 - 512 - a.static_ram_kib * 1024,
    'bootstrap_arena_bytes': APPLICATION_ARENA_BYTES,
    'bootstrap_source': str(bootstrap),
    'heapless_fde': fde,
    'status': 'prepared, requires successful target link and physical runtime validation'
}, indent=2))
print(a.output)
