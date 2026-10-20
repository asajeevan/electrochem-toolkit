# Landt / LANHE instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## NJK_CC_156_C30_C_x30.xlsx

- Source: https://github.com/be-smith/navani at commit d9892a3c982285173143aaab71c237869255e450, path `Example_data/NJK_CC_156_C30_C_x30.xlsx`
- Licence: MIT (text in `LICENSE-navani.txt`)
- Changes: unmodified copy
- Size: 2 360 950 bytes (source 2 360 950 bytes)
- What it is: Landt / LANHE Excel export with Record, Mode and Cycle sheets, 30 cycles of a coin cell, 62 305 rows. Kept whole (2.4 MB, above the 2 MB preference) because its Cycle sheet, the instrument's own statistics, is compared cycle by cycle. Profile landt-xlsx.
