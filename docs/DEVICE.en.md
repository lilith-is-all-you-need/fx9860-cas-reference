# Install and test on fx-9860GIII

Choose either calculator ZIP. Unzip on the PC and run python tools/verify_pair.py DIRECTORY from this checkout. Back up the previous KhiMap.g1a and KHICAS.BIN and your data. Copy the two files from one ZIP to storage root; both variants use the same names. Start KhiMap from the OS menu.

Compute 2+2. Record ordinary exit and direct MENU re-entry separately. A user reported first launch of the 699-page baseline and a Loading screen on direct re-entry. For the preview, try 1/2 and expand((x+1)^8). F6 Options switches input preview and output mode; F3 opens the viewer and F1 switches text. Exit, reopen and calculate again. Record OS, file hashes, final keys, exact screen and elapsed time. The preview still needs hardware acceptance.

For the original 2,094,444-byte English KhiCAS, match evidence/original-khicas.json and prepare a normal FxProfile folder. Use Full verification. If FlashLd reports No fitting OS block, preserve its program folder’s RUN.LOG through the first RUN_END. The known guest reservation is [0x88051000, 0x8807D000). Available contiguous OS blocks vary by session. For the specialized historical KLoad, supply your own matching original and use the separate preparation script under original-khicas/kload.
