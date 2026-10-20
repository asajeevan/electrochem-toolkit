# Novonix instrument exports: attribution

Real instrument export files copied from open-source repositories for the P08d compatibility work (docs/P08d_Instrument_Compatibility_Matrix.md). Each file is distributed here under the licence of the repository it came from; the full licence text is the LICENSE-<repository>.txt file beside it. None of these repositories states a separate licence for its test data, so the repository licence is taken to cover it. manifest.json records the SHA-256 of every shipped file and of its source, and tests/test_readers_real_files.py checks the shipped bytes against it.

## sample_data_novonix.csv

- Source: https://github.com/ImperialCollegeLondon/PyProBE at commit b5a789ebfceba4d68caa2f77322ea657c0e3422e, path `tests/sample_data/novonix/sample_data_novonix.csv`
- Licence: BSD-3-Clause (text in `LICENSE-PyProBE.txt`)
- Changes: unmodified copy
- Size: 42 575 bytes (source 42 575 bytes)
- What it is: Novonix UHPC CSV with [Summary], [Protocol] and [Data] sections, one constant-current charge, 207 rows. Profile novonix-csv.
