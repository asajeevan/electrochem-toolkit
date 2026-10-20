# Neware instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## neware_uio.csv

- Source: https://github.com/jepegit/cellpy at commit 29d916cb08e919a8bcd80f90892b906e8db49f2e, path `testdata/data/neware_uio.csv`
- Licence: MIT (text in `LICENSE-cellpy.txt`)
- Changes: unmodified copy
- Size: 1 922 549 bytes (source 1 922 549 bytes)
- What it is: Neware BTS flat CSV export (one row per record), hh:mm:ss times, 4 cycles, 9 065 rows (University of Oslo). Profile neware-csv.

## sample_data_neware_rows_2_25001.xlsx

- Source: https://github.com/ImperialCollegeLondon/PyProBE at commit b5a789ebfceba4d68caa2f77322ea657c0e3422e, path `tests/sample_data/neware/sample_data_neware.xlsx`
- Licence: BSD-3-Clause (text in `LICENSE-PyProBE.txt`)
- Changes: derived: the header row and worksheet rows 2 to 25001 of sheet 'record' kept, cell XML unchanged except that kept rows are renumbered from 2 and the sheet dimension and selection are updated; every other part of the workbook copied unchanged
- Size: 1 219 490 bytes (source 50 280 170 bytes)
- What it is: Neware BTS Excel export, sheet 'record', the first 25 000 records: a CC-CV charge and the following rest. Profile neware-xlsx.

## sample_data_neware_rows_80001_90000.xlsx

- Source: https://github.com/ImperialCollegeLondon/PyProBE at commit b5a789ebfceba4d68caa2f77322ea657c0e3422e, path `tests/sample_data/neware/sample_data_neware.xlsx`
- Licence: BSD-3-Clause (text in `LICENSE-PyProBE.txt`)
- Changes: derived: the header row and worksheet rows 80001 to 90000 of sheet 'record' kept, cell XML unchanged except that kept rows are renumbered from 2 and the sheet dimension and selection are updated; every other part of the workbook copied unchanged
- Size: 545 791 bytes (source 50 280 170 bytes)
- What it is: The same workbook, records 80 001 to 90 000: a charge during which Total Time passes 24 h and Excel switches the cell from a time of day to a 1900 date. Profile neware-xlsx.

## test.nda

- Source: https://github.com/be-smith/navani at commit d9892a3c982285173143aaab71c237869255e450, path `Example_data/test.nda`
- Licence: MIT (text in `LICENSE-navani.txt`)
- Changes: unmodified copy
- Size: 123 655 bytes (source 123 655 bytes)
- What it is: Neware .nda binary. Shipped as an example of a format this version does not read ('binary_export').

## test.ndax

- Source: https://github.com/be-smith/navani at commit d9892a3c982285173143aaab71c237869255e450, path `Example_data/test.ndax`
- Licence: MIT (text in `LICENSE-navani.txt`)
- Changes: unmodified copy
- Size: 39 718 bytes (source 39 718 bytes)
- What it is: Neware .ndax binary (a zip container). Shipped as an example of a format this version does not read ('binary_export').

## Truncation and derivation

A truncated text file keeps the first N lines of the source byte for byte. A derived workbook keeps the header row and one contiguous range of rows of the record sheet; the cell XML of those rows is unchanged except for the row numbers, the sheet dimension and the selected cell are updated, and every other part of the workbook is copied unchanged. The licences above (MIT, BSD-3-Clause) permit modified redistribution with the copyright notice kept.
