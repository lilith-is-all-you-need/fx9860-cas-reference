"""Preserve initial soft48 evidence; create an explicitly asserted soft24 bridge."""
from pathlib import Path
import hashlib,json
OUT=Path('/root/khicas-work/symbol-transaction-20261114')
old=OUT/'giac_bridge.cc'; new=OUT/'giac_bridge24.cc'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
text=old.read_text()
assert text.count('const size_t total_heap_limit = 48 * 1024;')==1
text=text.replace('const size_t total_heap_limit = 48 * 1024;',
    'const size_t total_heap_limit = 24 * 1024;\n'
    'static_assert(total_heap_limit == 24 * 1024, "Calculator CAS tracking must remain 24 KiB");')
assert not new.exists()
new.write_text(text)
record=dict(initial_bridge_sha256=digest(old),initial_actual_tracker_limit=49152,
    corrected_bridge_sha256=digest(new),corrected_tracker_limit=24576,
    physical_arena_bytes=32768,parent_test_storage_bytes=33024,independent_window_bytes=8192,
    initial_profiles_retained=['static-unit','static-unit-v2','static-unit-v3','formal-strict'],
    note='Initial CABI formal-strict was mislabelled soft24; source was actually soft48. Native/host unit tests do not call the bridge. Old sources, objects and reports remain unchanged.')
(OUT/'soft24-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
