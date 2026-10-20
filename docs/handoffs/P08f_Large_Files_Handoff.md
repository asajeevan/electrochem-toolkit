# P08f: large exports read as a stream. Handoff

Date: 2026-10-20. Status: **implemented and tested** (software tests and parser equivalence
against a reference captured from the previous reader; measured on synthetic large files). Not
experimentally validated on a real large export: none is shipped.

## What changed

- `electrochem/readers/reader.py`: the grid is no longer materialised. A text file is decoded in
  4 MiB blocks (incremental decoder), split into lines where `str.splitlines` splits, the header
  located in a first pass that stops at it, and every row passed through `csv` once; workbook
  sheets are streamed from openpyxl. Rows go a chunk at a time (16 384) into `_Grid`, which keeps
  only the columns a binding can use (float64 arrays built chunk by chunk; the step type as
  strings sharing one object per value; durations through `cells.parse_duration`) and counts for
  the shape checks. The binding loop is now `_bind` and is also run before any row is read, once
  for each width the header can still take, to learn which columns to keep. Numbers are
  converted a chunk at a time by `float()` where `_numbers_fast` can prove the result equals the
  per-token rule, otherwise per token by the unchanged `_to_float` (pieces of 1024 rows). SHA-256
  is computed while reading. Everything downstream of the grid (sign, capacity semantics,
  counter against integral, plausibility) is unchanged.
- `read(path, profile, progress=None)`: new optional callback, see API.
- `MAX_BYTES` raised from 512 MiB to 2 GiB (commented: a guard against a wrong file, no longer a
  memory bound).
- New refusal `invalid_layout` (see Decisions 2).
- `electrochem/readers/workbook.py` (new): `open_workbook(path)`, openpyxl's read-only load with
  each sheet sized from parser start events. For a sheet that declares no dimension, openpyxl
  otherwise parses the whole sheet once at load before the first row (42 of 105 s in a profile of
  a 200 000-row workbook). Same dimension found; openpyxl's method is restored after loading
  (lock and depth count); if openpyxl's internals differ, the workbook loads unchanged.
- `electrochem/readers/propose.py`: the table is found in the first 8 MiB of a text file (whole
  lines) or the first 2000 rows of each sheet (larger sheets sized from their declared
  dimension); the conventions are measured on the first 200 000 data rows; when the table is
  longer, `measured` gains `rows_measured` and `rows_total_estimate`, `rows` becomes the
  estimate, and a question says the rest was not measured. `detect_layout` keeps its signature.
- Tests (new): `tests/test_readers_reference.py` (the equivalence gate, 344 tests),
  `tests/test_readers_large.py` (2 000 000-row CSV: memory, time, values; workbook sizing),
  `tests/reader_corpus.py` (299 deterministic synthetic cases, workbooks made byte-stable),
  fixture `tests/fixtures/reader_reference/` (`reference.json`, `arrays.npz`, about 3 MB),
  capture script `scripts/capture_reader_reference.py`. No existing test was changed.
- Documents: `docs/P08d_Instrument_Compatibility_Matrix.md` section 9 (new);
  `docs/P08a_Import_Failure_Mode_Register.md` section 3.7 (new: `invalid_layout`; the 2 GiB limit).

## API

```python
electrochem.readers.read(path, p: ImportProfile, progress: Callable[[int, int, int], None] | None = None) -> RawTable
#   progress(rows_read, bytes_read, bytes_total): once per chunk of 16 384 rows and once at the
#   end (bytes_read == bytes_total). Workbooks: bytes_read estimated from rows read and the
#   sheets' declared dimensions.
electrochem.readers.reader.MAX_BYTES = 2 * 1024 ** 3
electrochem.readers.reader.BLOCK_BYTES, CHUNK_ROWS, SNIFF_ROWS   # 4 MiB, 16 384, 200; change no result
electrochem.readers.workbook.open_workbook(path)                 # load_workbook(read_only=True, data_only=True)
electrochem.readers.propose.DETECT_BYTES, DETECT_SHEET_ROWS, MEASURE_ROWS   # 8 MiB, 2000, 200 000
Proposal.measured["rows_measured"], ["rows_total_estimate"]      # present only when the table was sampled;
                                                                 # measured["rows"] is then the estimate
```

`RawTable`, `ImportProfile`, `Layout`, `Binding`, `Conventions`, `detect_layout`, `propose`,
`looks_tabular`, `_to_float`, `_sniff_decimal`, `interleaved_columns` and `_match` are unchanged.
Readers still import no engine module.

## Evidence

- Equivalence (`tests/test_readers_reference.py`), against the reference captured from the
  reader before any change: 21 vendor files (arbin, maccor, neware, basytec, novonix, pec, landt;
  the identified profile, the table or the refusal, the unsigned re-read of the two rest-only
  Maccor files, the proposal), 14 BioLogic exports through the generic engine, 299 synthetic
  cases. Every array identical (`np.array_equal(equal_nan=True)`, same dtype; NaN-canonical
  SHA-256 for every array, stored arrays for the real files), step kinds, columns, report and
  every finding (code, severity, message, detail, order) identical; the corpus also read with
  5-byte blocks and 3-row chunks. Nothing could not be made identical. A randomised test checks
  the chunk conversion against `_to_float` token by token (Unicode digits and spaces, U+001C to
  U+001F, `nan`, `inf`, `1_000`, d/D exponents, both decimal marks, NUL).
- The requested battery (`tests/test_readers_import.py ... tests/test_readers_variants.py`):
  `314 passed, 2 skipped in 73.64s (0:01:13)` (the baseline before the change was
  `314 passed, 2 skipped in 58.58s`).
- All reader suites, final run (`timeout 1800 python -m pytest -q tests/test_readers_*.py -p no:cacheprovider`):
  `660 passed, 2 skipped in 146.50s (0:02:26)`.
- Measurements (this machine, 2 cores, 7 GB; peak = VmHWM of the reading process alone, of which
  about 42 MB is the interpreter and imports; `ru_maxrss` was not used because on Linux it carries
  the parent's resident size across fork and exec):

  | File | Before P08f | Streaming reader |
  |---|---|---|
  | Arbin CSV, 2 000 000 x 14, 273 MiB | 3940 MB, 25.7 s | 322 MB, 11.7 s |
  | Arbin CSV, 500 000 x 14, 67 MiB | 1008 MB, 6.7 s | 152 MB, 2.9 s |
  | Arbin workbook, 200 000 x 15, no dimension | 291 MB, 45.8 s | 118 MB, 19.8 s (34.6 s before `open_workbook`) |
  | Arbin workbook, 1 000 000 x 15, no dimension, 63 MiB | not measured | 257 MB, 107.7 s |
  | the same with a dimension, 572 MiB | refused at 512 MiB | 254 MB, 106.7 s |

  The 572 MiB size is an artefact of my dimension-injecting script, which stored the zip entries
  uncompressed; the original reader refused it on size alone and was not rerun. In
  `test_readers_large.py` (2 000 000 rows, cold, before the column hand-over that took the peak
  from 413 to 322 MB) the printed line was: `[P08f] 2,000,000 rows x 14 columns, 273 MiB: read in
  18.9 s, peak resident memory 413 MB (interpreter and imports before reading: 42 MB), 124 progress
  calls`. The test asserts below 90 s and 1.5 GB. On the 2 000 000-row CSV, `Registry.identify`
  took 0.63 s and `propose` 3.48 s.

## Decisions made (reversible)

1. Equivalence is the gate: the reference was captured from the unchanged reader; the reader
   copy used is kept nowhere in the tree, the capture script is. To recapture after an intended
   change of behaviour, run the script and record why.
2. `invalid_layout` refuses `header_row` below 1 (without `header_contains`), a negative
   `unit_row` or a negative `skip_rows_after_header`. The old reader indexed its row list with
   these (`header_row=0` took the last line as the header); no layout means that, and the
   streaming reader cannot honour it cheaply. No built-in or proposed profile produces them.
3. A missing header or unit row still raises `IndexError` as before (not an `ImportFailure`); kept
   for identity. Worth turning into a named refusal later.
4. The chunk conversion uses `float()` itself (numpy's object cast), not numpy's own string
   parser, so values are bit-identical on every platform.
5. Workbook sizing is patched only while our own loads run, and gives openpyxl's own result.
6. The proposer reports the estimated total as `measured["rows"]` for a sampled file, so the
   window's row count stays meaningful; `rows_measured` says how many rows were looked at.

## Limits

- Workbooks: about 7 microseconds per cell in openpyxl's XML parsing; a million-row sheet takes
  close to two minutes, bounded in memory. A CSV export reads more than ten times faster per row.
- Memory grows with rows times bound columns (8 bytes a value) plus 8 bytes a row for the step
  type; `MAX_BYTES` (2 GiB) is a guard against a wrong file.
- A skipped worksheet is read only as far as the header search (100 rows): damage beyond that no
  longer raises.
- The proposer chooses the delimiter on the 8 MiB it reads; its row total is an estimate (blank
  lines counted).
- Not verified on a real large export (none available); the memory and time figures are from
  synthetic Arbin-like files.

## Progress in the window (main session, same day)

Wired as proposed: `workflow.open_file(..., progress=None)` and `open_with_profile(..., progress=None)`
pass the callback to `read`; `worker.in_process(fn, *args, progress=None)` accepts a text callback. In
thread mode the reader's `(rows, bytes_read, bytes_total)` is turned into words by `worker._text_progress`
(at most five a second); in process mode the child puts the tuples on a `multiprocessing.Manager().Queue()`
(`_QueueProgress`, at most five a second) and the worker thread that waits on the future drains it and
emits the same signal, so the GUI thread only ever receives text. `app.py` connects it to
`_reading_progress`, which rewrites the reading screen's current line in place (`Telemetry.progress`, a
line of kind "progress") and the status bar. Measured in process mode on an 859 000-row Arbin CSV
(113 MB, the shipped `.res` table export repeated): 26 updates, read in 9.0 s, the screen's line ending
at "Reading: 858,942 rows, 100 % of the file". Tested in thread mode (`tests/test_studio.py`,
`test_reading_a_file_from_another_cycler_reports_its_progress_in_place`).

Found on the way, and fixed: with more than 100 000 rows the time views set clip-to-view before adding
the curve to its plot, and pyqtgraph 0.14 then looked the curve's view up while the scene adopted it
(before the ViewBox was its parent) and asked the PlotWidget for `autoRangeEnabled`: an `AttributeError`
on every large file, in the Overview, Timeline and Data views. The curve is now configured after
`addItem` (`views.py`); `test_a_large_table_draws_in_every_view_without_an_error` opens a 119 514-row
EC-Lab file in every view and fails on the old order.

## Next actions

- A named refusal in place of `IndexError` for a missing header or unit row (an intended change:
  recapture the reference).
- A real large export (an Arbin or Neware CSV of a long test) as evidence for this row of the matrix.

## EC-Lab files and the engine (main session, same day)

The same question applies to EC-Lab files and to the engine, and both were measured before anything was changed.

**Measured first.** A 1 000 000-row `.mpt` (the demonstration file repeated 50 times, 133 MB, 16 columns) took 33 s and 2.1 GB to open: the P03 text importer keeps one pydantic record per row with every token as a string, and `table._floats` matched every token against a regular expression in a Python loop. The native path was worse per row (one record per row with the hex of every field and its decoded text). Segmenting a 2 000 000-row table took 8.1 s, of which 7.8 s were the row-by-row loop of `segment.edges` and 1.5 s the loop of `segment.branches`; `cycling.analyse` on the same table took 0.65 s.

**What changed.**

- `electrochem/table.py`: two fast paths in `load()`, used by the app and the command line. `_fast_text` reads a signed EC-Lab export's header lines as before, then hands the data block to numpy's C parser (`np.loadtxt`, the needed columns only); EC-Lab's `XXX` is counted and read as not-a-number exactly as the strict path does; a decimal comma is handled by replacing it in the data block. `_fast_native` builds the Table straight from the decoded record array of the pinned galvani reader, with the same integrity checks and failure codes as `inspect_native` (module bounds, record bytes reproduced, one data module, record count), without per-row records. Both step aside, returning None so that the strict P03 importers run, whenever the block holds anything they do not handle: any letter other than an exponent's e/E or `XXX` (numpy would accept `nan` and `inf`, the strict path counts them invalid), bare carriage-return line endings, a short row. So no file is read by a looser rule than before, and `load(path, fast=False)` is the strict path itself, kept for cross-checks. The 256 MiB limit of the P03 importers no longer applies on the fast path (2 GiB).
- `electrochem/segment.py`: `edges()` and `branches()` vectorised; the rules and their order of precedence are unchanged.
- `tests/test_table_fast_path.py` (21 tests): the fast path's Table equals the strict importer's bit for bit on every public `.mpt` and `.mpr` and the demonstration file (every array, the potentials, columns, labels, invalid-token counts, header, hash); the `XXX` case (`bio_logic5.mpt`: one invalid time token, counted in the same column); a decimal-comma export made from the formation file; an `inf` token and bare carriage returns take the strict path; a 200 000-row export reads in under ten seconds. `tests/test_segment_speed.py`: the vectorised `edges()` and `branches()` against the row-by-row rules, kept in the test as the specification, on 250 random tables that exercise every rule (time resets, duplicate times, missing current, error flags, sign changes across step boundaries, rests, zero current inside an active stretch, the last branch at the end of the file; 1128 comparisons, 72 refused identically); a 2 000 000-row table segmented in under two seconds with the built-in branch count and first-cycle charge.
- The author's own files (private, not in the repository): the fast path equals the strict path on both the `.mpr` and the 31 MB `.mpt`, in 0.05 s and 0.5 s instead of 4.0 s and 2.6 s.

**Measured after.** The 1 000 000-row `.mpt`: 2.7 s and about 0.5 GB (the file's bytes, the decoded header and the float arrays). The 2 000 000-row table: segmented in 0.17 s, analysed in 0.65 s; the whole analysis of such a file is now bounded by reading it. The window draws large tables with pyqtgraph's peak downsampling and clip-to-view from 100 000 rows (unchanged; display never changes a number).

**Limits.** The whole file is still read into memory once (the bytes, then the arrays): a 2 GiB export needs about 3 GiB of memory. A streaming reader that never holds the bytes would be the next step if files beyond that appear; the readers for other cyclers (above) already stream.
