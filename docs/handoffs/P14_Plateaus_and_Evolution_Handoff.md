# P14 handoff: dQ/dE peaks, pairing, plateau descriptors and evolution figures

20 October 2026. Question from the user: "What happens when there are 3 or 4 reversible plateaus and 2 or 3 irreversible plateaus? How do you calculate each mean potential and how do you report irreversible peaks? Is there any possibility of advanced 3D plots?"

Status: **implemented and tested** (software tests against a synthetic cell with known answers, smoke tests on two other files). **Not experimentally validated.** The method specification is M01 sections 9 and 10.

## Short answer to the question

- Each plateau gives a dQ/dE peak; the tables give its potential (a descriptor at the applied rate), the capacity under it (between the valleys on either side), its share of the branch, its partner in the opposite branch of the same cycle (nearest within 200 mV, greedy), the separation and apparent mid-point of the pair, and the cycles in which it is present.
- The mean potential of a branch is unchanged: energy / charge, the charge-weighted mean potential ∫E dQ / ∫dQ, which for several plateaus is the capacity-weighted mean of the plateau potentials, Σ Q_i E_i / Σ Q_i. No other "mean" is formed from peak potentials.
- A peak that does not return is reported as what the data show: "unpaired: no counterpart within 200 mV in the discharge of the same cycle" and, across cycles, "first cycle only" or "appears from cycle k". Nothing is called irreversible; `summary.json` lists unpaired and first-cycle-only peaks of the reference cycle.
- 3D: figure 7 draws dQ/dE as two 3D surfaces (charge, discharge) with cycle number as depth; figure 6 is the same grid as a colour map, the form to read numbers from; the app has an Evolution view (map and waterfall).

## What changed (files)

| File | Change |
|---|---|
| `electrochem/differential.py` | `DqdvCurve.capacity` (grid capacity, optional field) and `capacity_unit`, `grid_capacity()`; `peak_search`, `peak_windows`, `peak_charges`, `curve_capacity`, `pair_peaks`, `Track`, `track_peaks`, `cycle_ranges`, `evolution_text`, `PlateauPeak`, `PeakPair`, `PlateauReport` (`peak_rows`, `pair_rows`, `summary`), `plateau_analysis`, `describe_peak`, `DqdeGrid` (`filled`, `value`), `evolution_grid`, `grid_rows`; constants `PEAK_PAIR_WINDOW_MV`, `MIN_PROMINENCE_FRACTION`, `MAX_PEAKS`. `curve()` and `peaks()` keep their signatures and results. |
| `electrochem/cycling.py` | `Settings.peak_pair_window_mV: float = 200.0` (one field, at the end; requested by the coordinator); docstring "average voltage ... charge-weighted mean potential". |
| `electrochem/workflow.py` | `FIGURES` += `("7", "dqde_map", ...)`, `("8", "dqde_surface", ...)`; `FILE_STEMS`, `ORDER`; `Run.peak_pair_window_mV` (property, from the settings), `Run.all_cycles`, `Run.plateaus(cycles=None)`, `Run.evolution_grids(cycles=None)`; `analyse_file(..., peak_pair_window_mV=None)`; `ExportOptions.evolution_cycles = "all"`; `methods(s, dqde_mv, dqde_units, peak_pair_window_mV=200.0, evolution_cycles="all")` with new entries `dqde_peak_charge`, `dqde_pairs`, `dqde_presence`, `dqde_map` and the reworded `average_voltage` and `dqde_peaks`; figure builders `dqde_map`, `dqde_surface` (lazy: no curve is computed until drawn); export writes `dqde_pairs.csv`, `dqde_map.csv`, the extended `dqde_peaks.csv` (every cycle), `summary.json` → `plateaus`, `settings.json` → `differential` and `figure_style.evolution_cycles`. |
| `electrochem/plotting.py` | `fig6_dqde_map`, `fig7_dqde_surface`, `_frame_3d`, `MAP_CMAP`, `NOT_MEASURED`, `SURFACE_MAX_ROWS`; checker: `is_3d`, `_ticks_in_view`, `_data_outside_3d`, QuadMesh in `_data_outside`, `lightness`, `colour_order`, `colour_maps`, `_text_polygon`, `_polygons_overlap`; status "skip" documented. |
| `electrochem/origin_export.py` | `write_plateau_tables(odir, report)`: `origin/dqde_peaks.csv`, `origin/dqde_pairs.csv` (three-header layout); README lists them. |
| `electrochem/studio/views.py` | `EvolutionView(View)`. |
| `electrochem/studio/figures.py` | the two figures in `NAMES`/`ORDER`, `SHAPES` for the fit zoom, list height from `len(ORDER)`, a "dQ/dE map and surface" combo (every cycle / selected cycles), status "skip" shown with the info icon and counted in the verdict. |
| `tests/plateau_cell.py` (new), `tests/test_plateaus.py` (new, 18 tests), `tests/test_evolution_view.py` (new, 5 tests), `tests/test_figures.py` (14 tests appended) | see Evidence. |
| `docs/M01_Cycling_Method_Specification.md` | sections 9 and 10 appended. |

## Wiring in the window (main session, done the same day)

- `app.py`: `("Evolution", EvolutionView)` is in `VIEWS`, between dQ/dE and Voltage (Figures is now Ctrl+9). The
  compact view switcher was tightened so all nine buttons keep their whole names at 1024 x 600
  (`test_finding26_nothing_is_cut_off_from_the_smallest_window_up`).
- `inspector.py`: a *Plateaus, cycle n (dQ/dE peaks)* block under the focused cycle's values: each pair with its
  two potentials, separation and the capacity under each peak; each unpaired peak with its note and its presence
  across cycles ("present in the first cycle only", "appears from cycle k"); capped branches; one line on what the
  descriptors are. `Run.plateaus()` caches the every-cycle report per run, since the inspector rebuilds often.
  Tested on the synthetic cell (`tests/test_studio.py`,
  `test_the_inspector_reports_the_plateaus_of_the_focused_cycle_in_factual_words`: three pairs at 60 mV, the 4.10 V
  first-charge peak unpaired and first cycle only, the 2.68 V peak appearing from cycle 3, no "irreversible").
- `analyze.py`: `--peak-pair-window-mv`.
- `methods_text.py` (Help > How the numbers are calculated): the peaks topic names every new column, the pairing and
  tracking rules and the window, imports the thresholds from `differential.py`, and under *For this file* gives the
  reference cycle's pairs, unpaired and first-cycle-only peaks.

## Exact new columns (for the "Where it appears" text)

- `dqde_peaks.csv`: `cycle, branch, direction, peak, voltage_V, dqdv, prominence, width_V, basis, bin_mV` (unchanged, first), then `charge, charge_unit, share_of_branch_pct, curve_capacity, window_low_V, window_high_V, partner_voltage_V, separation_mV, midpoint_V, pairing, pairing_note, pair_window_mV, track, cycles_seen, evolution, peaks_found, peaks_reported, capped, peaks_note`.
- `dqde_pairs.csv`: `cycle, pair, charge_peak, discharge_peak, charge_voltage_V, discharge_voltage_V, separation_mV, midpoint_V, charge_capacity, discharge_capacity, capacity_unit, pair_window_mV, bin_mV`.
- `dqde_map.csv`: `cycle, direction, basis`, then one column per node potential in V.
- `summary.json` → `plateaus`: `cycle, pair_window_mV, bin_mV, pairs, pair_potentials_V, unpaired_peaks, first_cycle_only_peaks, peaks_appearing_later, capped_branches, note` (+ `notes`).
- `settings.json`: `settings.peak_pair_window_mV`; `differential` = `bin_mV, peak_pair_window_mV, min_prominence_fraction, max_peaks, peak_notes`; `figure_style.evolution_cycles`; `methods` keys `dqde_peaks, dqde_peak_charge, dqde_pairs, dqde_presence, dqde_map`.

## Decisions (reversible)

1. The window lives in `Settings.peak_pair_window_mV` (default 200 mV); `Run.peak_pair_window_mV` reads it. `analyse_file(peak_pair_window_mV=...)` replaces it in the run's copy of the settings.
2. Peak tables cover every cycle (presence across cycles needs the whole record); `dqde_curves.csv` keeps the plotted cycles.
3. Charge under a peak uses the grid capacity, valley-to-valley (rule in M01 9.3), shared valleys between neighbours; share relative to the capacity the dQ/dE curve spans (constant-voltage stages excluded, since dQ/dE is undefined there).
4. Presence across cycles is by tracks (nearest within the window, one peak per track per cycle, tracks survive gaps); for peaks farther apart than the window this equals the literal rule "no peak within the window in any later cycle"; with closer peaks it keeps a new neighbour from being merged into an old peak.
5. The evolution grid resamples each curve onto nodes at multiples of the bin (shift below one bin) rather than changing `curve()`, so no existing number moved.
6. Map colour `magma_r` (sequential, monotonic lightness, zero paper-light); not-measured cells grey.
7. Figure 7 has two panels (charge, discharge) instead of one signed surface: in one box the zero plane of the charge surface hid the discharge peaks (seen in the first prototype). Every potential node drawn; above 120 cycles every k-th cycle, stated on the figure.
8. Figure numbering: CLI keys 7 and 8 (key 6 is the summary); file stems `fig6_dqde_map`, `fig7_dqde_surface`, matching the function names asked for.
9. The checker's twelve checks all apply to 3D axes after adaptation (M01 section 10); "skip" exists for when a 3D attribute cannot be read.
10. (Main session, same day.) Both panels of figures 6 and 7 share one potential range, the union of the two directions' grids, so a pair lines up vertically; beyond a direction's own range the map panel is grey (not measured). Figure 7 names the height on its first panel only; the colour bar names it beside the second. `tests/test_figures.py::test_both_panels_of_the_evolution_figures_share_one_potential_scale`.

## Evidence

- Full suite, `timeout 1800 python -m pytest -q tests -p no:cacheprovider -x`, verbatim: `911 passed, 2 skipped, 56 subtests passed in 424.17s (0:07:04)`. (One earlier run stopped at `tests/test_readers_variants.py::test_a_renamed_column_asks_again_but_starts_from_the_saved_profile` while `electrochem/readers/propose.py` was being edited by the readers agent; that test passed alone and in the rerun above.)
- New tests: `tests/test_plateaus.py` 18 passed, `tests/test_evolution_view.py` 5 passed, the 14 appended to `tests/test_figures.py` passed (run separately before the full suite).
- Synthetic cell results (bin 10 mV): worst peak-potential error 4.7 mV (half a bin is 5 mV); pair separations 60.0 mV; branch means equal to the constructed ∫E dQ / Q within 1.3 µV, and within 2.0 mV of Σ Q_i E_i / Σ Q_i (the linear background accounts for the difference); peak capacities equal Q_i plus the background inside each window within 1 % (main plateaus within 2 % of Q_i; the 0.04 mAh plateau carries 5 % background).
- Mutation checks: reordering the pairing candidates, and scaling the peak charge by 4 %, each made tests fail; restored.
- All new and existing figures pass `check_figure` for Nature and Elsevier on the plateau cell, the demonstration file (50 cycles) and the formation file (2 cycles); figure PDFs are 120.0 mm (map) and 183.0 mm (surface) wide.
- Visual inspection of rendered PNGs of both figures and of the view (light and dark themes, offscreen grabs).

## Limits

- Not experimentally validated; peak descriptors are rate- and polarisation-dependent; pairing by proximity is a convention; plateaus closer than about two bins merge; a plateau split by a rest or a current change is two peaks; capacity in constant-voltage stages has no peak; the charge under a small peak includes the background in its window.
- The colour scales are linear (small peaks faint). 3D surfaces hide what lies behind a ridge; numbers should be read from the tables, the map readout or `dqde_map.csv`.
- `check_figure` tests text and legends against the projected 3D drawing in display space; depth occlusion is not considered. Rotated-label overlap uses the rotated rectangle recovered from the axis-aligned box; within about 6° of 45° it falls back to the box (conservative).
- The Evolution view computes all curves on the interface thread when first shown (0.02 s for the 50-cycle demonstration file here; proportionally longer for long tests).
