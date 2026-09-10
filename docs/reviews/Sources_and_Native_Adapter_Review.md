# P03 inspected sources and native-reader decision

Date: 2026-09-10. Scope: text-layout contract and bounded native-reader evaluation. No new reading of the supplied scientific PDFs was necessary for byte/column import; prior scientific access claims are unchanged.

## Instrument documentation inspected

Bio-Logic, EC-Lab Software User's Manual, version 10.38, August 2014, section 5.2.1, printed pp. 174–175 (PDF indices 179–180), inspected through a [Caltech-hosted manufacturer manual](https://mmrc.caltech.edu/BioLogic%20Echem/ECLab%20Manuals/EC-Lab%20software%20user%27s%20manual.pdf). It describes MPT text export, elapsed/absolute-time choices and selected cycle/loop export. Therefore an MPT filename does not establish whole-run coverage or numeric elapsed-time semantics. This is historical official documentation, not proof that all current versions use the same layout. A direct BioLogic-hosted manual URL was inaccessible; no claim of inspecting a current manual is made. Signatures/header counts and trailing-field conventions are grounded additionally in the exact public fixtures, not claimed as a complete formal vendor specification.

## Native options

| Candidate and inspected source | Evidence and decision |
|---|---|
| [Galvani README](https://github.com/echemdata/galvani/tree/d4a5f444b16eae57d2edfad6df774ead95c92fd6), `setup.py`, BioLogic module license header and scoped tests | GitHub checkout d4a5f444b16eae57d2edfad6df774ead95c92fd6, dated 2025-07-30, package metadata 0.5.0. Python code declares GPL-3.0-or-later and runtime NumPy. Public MPR decoding was executed on five same-stem MPR/MPT candidates. This is a promising evaluated reader, not an integrated dependency. README points development to Codeberg; that site was blocked by robots during browsing, so this GitHub checkout is not claimed to be the latest upstream. |
| [eclabfiles repository](https://github.com/vetschn/eclabfiles) | Inspected README/archive notice: archived July 2024, with maintainers directing users to yadg. No runtime test or dependency selected. |
| [yadg EC-Lab development documentation](https://dgbowl.github.io/yadg/main/apidoc/yadg.extractors.eclab.html) and [project metadata](https://github.com/dgbowl/yadg/blob/main/pyproject.toml) | Inspected MPR/MPT API, timezone/encoding inputs, project license and dependencies. Project metadata declares GPL-3.0-or-later; dependencies include NumPy, Pint, pandas, xarray and HDF5-related packages. Documentation is marked 7.0.dev2, not a pinned release. No runtime/Windows test was performed. Candidate for broader metadata extraction, requiring a pinned release and compatibility comparison before adoption. |

The project distribution license remains undecided. The text importer adds no dependency beyond the existing P01 stack. There is no finding that GPL software is scientifically unsuitable: obligations and distribution choices must be resolved explicitly if an adapter is incorporated. Neither subprocess separation nor an optional install is asserted to remove license obligations. No third-party parser implementation was copied.

## Public fixture provenance

- Galvani `tests/testdata/*.mpt`, revision above: CC-BY-4.0 dataset notice in `.reuse/dep5`; preserve Christopher Kerr attribution and the file-specific Chihyu Chen notice for `020-formation_CB5.mpt`. Copied data are unchanged. Included attribution and license files identify terms.
- [PyProBE test data](https://github.com/ImperialCollegeLondon/PyProBE/tree/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/tests/sample_data/biologic), BSD-3-Clause repository notice included. Six unmodified text fixtures, including headerless and timestamped variants.
- [BEEP settings fixture](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/tests/test_files/BioTest_000001.mps), Apache-2.0 repository notice included. One unmodified MPS used only for settings-context recognition.

Exact copied paths, source revisions, hashes and explicit import profiles are in `public_data/manifest.json`. These source repositories supplied test artifacts, not research validation endorsements. Matching filenames are candidate relationships only; row alignment must be checked independently.
