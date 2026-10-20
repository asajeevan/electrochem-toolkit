# Maccor instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## xTESLADIAG_000038con.078

- Source: https://github.com/TRI-AMDD/beep at commit f2b984e4bbf54554d9514c1defc81d09ac2a3dee, path `tests/test_files/xTESLADIAG_000038con.078`
- Licence: Apache-2.0 (text in `LICENSE-beep.txt`)
- Changes: unmodified copy
- Size: 1 033 423 bytes (source 1 033 423 bytes)
- What it is: Maccor text export, 'Test (Sec)' time column, signed Amps, 8 cycles, 3 873 rows. Profile maccor-export-sec.

## PredictionDiagnostics_000151_test.052

- Source: https://github.com/TRI-AMDD/beep at commit f2b984e4bbf54554d9514c1defc81d09ac2a3dee, path `tests/test_files/PredictionDiagnostics_000151_test.052`
- Licence: Apache-2.0 (text in `LICENSE-beep.txt`)
- Changes: unmodified copy
- Size: 90 743 bytes (source 90 743 bytes)
- What it is: Maccor text export, 'Test (Sec)', a 333-row slice starting at record 249 791 in cycle 37, in the middle of a discharge. Profile maccor-export-sec.

## maccor_example.001

- Source: https://github.com/ROVI-org/battery-data-toolkit at commit 19961e6bbb2d0cfe0bff9c129144fcf8f3dd3be6, path `tests/files/maccor_example.001`
- Licence: Apache-2.0 (text in `LICENSE-battery-data-toolkit.txt`)
- Changes: unmodified copy
- Size: 1 206 bytes (source 1 206 bytes)
- What it is: Maccor (Argonne MIMS) text export, 'Test (Min)' time column, 8 rows of rest. Recognised by maccor-export-min; the import then stops because a rest-only file cannot show which sign is charge.

## maccor_001_first_cycle.txt

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `testdata/data/maccor_001.txt`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: truncated: the first 2761 lines of 6708 kept byte for byte, nothing else changed
- Size: 1 459 431 bytes (source 3 550 877 bytes)
- What it is: Maccor text export with clock-format TestTime ('0d 00:00:5.05...'), unsigned Amps and a State column (University of Birmingham, SIMBA project). Profile maccor-export-clock.

## maccor_002.txt

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `testdata/data/maccor_002.txt`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: unmodified copy
- Size: 1 524 544 bytes (source 1 524 544 bytes)
- What it is: Maccor text export with a 12-line header block, 'Cycle P', 'Cap. [Ah]', 'Md', decimal point, TestTime in minutes (KIT, SIMBA project), 7 446 rows. Profile maccor-txt.

## maccor_two.txt

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `examples/data/maccor_two.txt`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: unmodified copy
- Size: 42 972 bytes (source 42 972 bytes)
- What it is: Same layout as maccor_002.txt with a decimal comma; rest only, and the last line is cut off mid-number. Recognised by maccor-txt; the import stops because a rest-only file cannot show which sign is charge.

## Truncation and derivation

A truncated text file keeps the first N lines of the source byte for byte. A derived workbook keeps the header row and one contiguous range of rows of the record sheet; the cell XML of those rows is unchanged except for the row numbers, the sheet dimension and the selected cell are updated, and every other part of the workbook is copied unchanged. The licences above (MIT, BSD-3-Clause) permit modified redistribution with the copyright notice kept.
