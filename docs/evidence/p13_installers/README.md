# Evidence for the installers

The files here belong to the delivered build of 0.8.0 (20 October 2026); `0.7.0/` keeps the morning's build of
the same day. `build_windows.log` and `build_macos.log` are the build's own log (pip command lines shortened);
`*.sha256` are the checksums of the files delivered; the four PNGs are the installer's pages photographed under
Wine and Xvfb.

Two builds of 0.8.0 were made. Build A (16:02) was tested in full: the Wine harness on its staged Windows tree
(imports, every view of the demonstration file, then the whole self-test suite with the bundled Windows
interpreter: 920 passed, 3 skipped, 12 min 52 s), and the install check below. Build B (16:31) is the one
delivered; it was made after `STATUS.md` and `docs/U02_Cyclara.md` were updated with A's results. Its staged
Windows tree was compared with A's file by file: 10 799 files, the same except those two documents and
`Cyclara.exe`, whose bytes differ only in the PE time stamp and the header checksum that mingw writes at link
time. B was then run under Wine (imports, every view) and install-checked. `wine_run_summary.txt` has both runs.

Install check (32-bit Wine, `/S`), for A and again for B: the morning's 0.7.0 installed first (10 759 files),
then 0.8.0 over it (39 s and 38 s); the installed tree equals the built stage file for file and byte for byte
(B: 10 799 files hashed), no file of 0.7.0 left behind, only `Uninstall.exe` added; Start menu and Desktop
shortcuts, the uninstall key (DisplayVersion 0.8.0) and the "Open with" registration present; `Uninstall.exe /S`
removed the folder, both shortcuts and the keys.
