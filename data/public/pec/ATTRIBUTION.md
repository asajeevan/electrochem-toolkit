# PEC instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## pec_first_cycle.csv

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `testdata/data/pec.csv`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: truncated: the first 11411 lines of 16288 kept byte for byte, nothing else changed
- Size: 1 988 193 bytes (source 2 798 037 bytes)
- What it is: PEC CSV export (2019), 'Total Time (Seconds)', mV and mA, a 44 Ah cell at C/25: the first discharge, one full cycle and the following rest. Profile pec-csv.

## Test25205.csv

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `testdata/data/pec_multiple_tests/Test25205.csv`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: unmodified copy
- Size: 113 316 bytes (source 113 316 bytes)
- What it is: PEC CSV export (2026), 'Total Time (Hours in hh:mm:ss.xxx)', open-circuit storage only. Profile pec-csv-clock.

## Truncation and derivation

A truncated text file keeps the first N lines of the source byte for byte. A derived workbook keeps the header row and one contiguous range of rows of the record sheet; the cell XML of those rows is unchanged except for the row numbers, the sheet dimension and the selected cell are updated, and every other part of the workbook is copied unchanged. The licences above (MIT, BSD-3-Clause) permit modified redistribution with the copyright notice kept.
