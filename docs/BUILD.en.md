# Build map

Open the loader CMake project under the selected integrations directory in FxStudio and build Release. Its expected header binds a specific external payload. The payload directory contains the target startup and runtime adapter. The original-KhiCAS KLoad project has a separate preparation workflow.

The release snapshot giac-source-and-relink-inputs.tar.gz contains the prepared math sources, TomMath sources, static input archives, headers, linker inputs and per-variant build plans. In an isolated Linux environment restore it under /root/khicas-work. The historical Linux big-endian SH GCC 14.1.0 and compatible LTO implementation must be available at the recorded paths. Inspect the compiler and input digests in build-plan.json and the arguments in commands.json. See NOTICE.md for the SDK and runtime source archives. The verification starting point is the frozen build environment; a full bootstrap of its cross-compiler from an empty host is a separate task.

Run python tools/relink.py --variant 699 --output NEW_DIR to inspect the plan, then use a fresh output directory and append --run to link. The 701 variant selects its distinct preview archive and project sources. Run the chosen loader project’s tools/prepare_image.py on the resulting raw payload in a disposable project copy. It prepends the 512-byte external header and updates src/expected.h. Build that loader and retain it with its exact KHICAS.BIN. Use tools/verify_pair.py for the published pairs. Compare the 699/701-page cases, runtime assumptions, re-entry behavior and verification status in the device guide and evidence catalog.


On 2026-11-19 both payloads were relinked in the preserved Linux environment. After the 512-byte header was added, both whole-file digests matched the recorded historical releases. The original-KhiCAS preparation script was also exercised against the matching original. [SHA-256](../evidence/relink-verification.json)

A separate verification exposed only the freshly extracted release snapshot at /root/khicas-work in an isolated mount namespace. Using the installed historical compiler, tools/relink.py reproduced both payload SHA-256 digests again.
