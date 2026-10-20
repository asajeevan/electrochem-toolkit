# Arbin instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## arbin_example.csv

- Source: https://github.com/ROVI-org/battery-data-toolkit at commit 19961e6bbb2d0cfe0bff9c129144fcf8f3dd3be6, path `tests/files/arbin_example.csv`
- Licence: Apache-2.0 (text in `LICENSE-battery-data-toolkit.txt`)
- Changes: unmodified copy
- Size: 284 095 bytes (source 284 095 bytes)
- What it is: Arbin .res channel table as CSV (column names without units), two cycles of the TRI fast-charge protocol, 2 142 rows. Profile arbin-res-table-csv.

## sample_data_arbin.csv

- Source: https://github.com/ImperialCollegeLondon/PyProBE at commit b5a789ebfceba4d68caa2f77322ea657c0e3422e, path `tests/sample_data/arbin/sample_data_arbin.csv`
- Licence: BSD-3-Clause (text in `LICENSE-PyProBE.txt`)
- Changes: unmodified copy
- Size: 1 996 bytes (source 1 996 bytes)
- What it is: Arbin MITS CSV export with spaced column names ('Test Time (s)'), 13 rows: rest and the first two rows of a charge. Profile arbin-mits8-csv.

## arbin.csv

- Source: https://github.com/Battery-Intelligence-Lab/galv-harvester at commit f790d1d45f5460336992e4334b58db19e9ab0d0d, path `.test-data/test-suite-small/arbin.csv`
- Licence: BSD-2-Clause (text in `LICENSE-galv-harvester.txt`)
- Changes: unmodified copy
- Size: 4 226 bytes (source 4 226 bytes)
- What it is: Arbin MITS Pro CSV export with underscore column names ('Test_Time(s)'); one rest row repeated 21 times by the source project, so it documents column names only. Profile arbin-csv.

## bs542_004_gr_li_50ua_50mv_1v_191020_Channel_11.xlsx

- Source: https://github.com/be-smith/navani at commit d9892a3c982285173143aaab71c237869255e450, path `Example_data/bs542_004_gr_li_50ua_50mv_1v_191020_Channel_11.xlsx`
- Licence: MIT (text in `LICENSE-navani.txt`)
- Changes: unmodified copy
- Size: 558 853 bytes (source 558 853 bytes)
- What it is: Arbin MITS Pro PV7.0 Excel export (Global_Info and Channel_11_1 sheets), graphite against lithium, one cycle, 4 526 rows. Profile arbin-xlsx.

## arbin_example.res

- Source: https://github.com/be-smith/navani at commit d9892a3c982285173143aaab71c237869255e450, path `Example_data/arbin_example.res`
- Licence: MIT (text in `LICENSE-navani.txt`)
- Changes: unmodified copy
- Size: 532 480 bytes (source 532 480 bytes)
- What it is: Arbin .res binary (a Microsoft Access database). Shipped as an example of a format this version does not read; it is refused with the reason 'binary_export'.
