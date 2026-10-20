"""How to cite Cyclara and electrochem-toolkit.

One source for every form of the citation: the plain reference, BibTeX, the
repository's CITATION.cff and the sentence for a methods section. All of them
read the version, the release date, the author and the URL from the package,
so a version bump changes every form at once and the test suite checks that
the committed CITATION.cff is the generated one.

    python -m electrochem.citation            print the plain reference
    python -m electrochem.citation --bibtex   print the BibTeX entry
    python -m electrochem.citation --cff      print CITATION.cff
    python -m electrochem.citation --write    rewrite CITATION.cff beside the package
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import __author__, __license__, __released__, __url__, __version__

FAMILY = "Shyma Sajeevan"
GIVEN = "Aswadh"
TITLE = "Cyclara: traceable analysis of battery cycling data"
SUBTITLE = ("Free software (GNU GPL v3 or later) that reads BioLogic EC-Lab files and the text or spreadsheet "
            "exports of other battery cyclers and produces journal figures, every table, an Origin folder and "
            "a settings record for each analysis. Cyclara is the window of the electrochem-toolkit package.")
CFF_PATH = Path(__file__).resolve().parents[1] / "CITATION.cff"


def year() -> str:
    return __released__[:4]


def plain() -> str:
    """The reference as a reference list wants it (author, year, title, version, kind, where)."""
    return (f"{FAMILY}, {GIVEN[0]}. ({year()}). {TITLE} (Version {__version__}) [Computer software]. "
            f"{__url__}")


def key() -> str:
    return "cyclara_" + __version__.replace(".", "_")


def bibtex() -> str:
    return "\n".join([
        f"@software{{{key()},",
        f"  author  = {{{{{FAMILY}}}, {GIVEN}}},",
        f"  title   = {{{{{TITLE}}}}},",
        f"  version = {{{__version__}}},",
        f"  year    = {{{year()}}},",
        f"  url     = {{{__url__}}},",
        f"  license = {{{__license__}}},",
        f"  note    = {{Free software under the GNU General Public License, version 3 or later}}",
        "}",
    ])


def cff() -> str:
    """The Citation File Format text (1.2.0), the file GitHub reads for its 'Cite this repository' box."""
    return "\n".join([
        "cff-version: 1.2.0",
        'message: "If this software contributed to a publication, please cite it with its version."',
        f'title: "{TITLE}"',
        f'abstract: "{SUBTITLE}"',
        "type: software",
        "authors:",
        f'  - family-names: "{FAMILY}"',
        f'    given-names: "{GIVEN}"',
        f"version: {__version__}",
        f"date-released: {__released__}",
        f"license: {__license__}",
        f'url: "{__url__}"',
        f'repository-code: "{__url__}"',
        "keywords:",
        "  - battery cycling",
        "  - electrochemistry",
        "  - BioLogic EC-Lab",
        "  - differential capacity",
        "  - data analysis",
        "",
    ])


def sentence() -> str:
    """One sentence for a methods section; the reference it points to is plain()."""
    return (f"Cycling data were analysed with Cyclara {__version__} ({FAMILY}, {year()}), free software under the "
            f"GNU General Public License, {__url__}.")


def all_forms() -> dict[str, str]:
    return {"Reference": plain(), "BibTeX": bibtex(), "CITATION.cff": cff(), "Methods sentence": sentence()}


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "--write" in args:
        CFF_PATH.write_text(cff(), encoding="utf-8")
        print(f"wrote {CFF_PATH}")
        return 0
    if "--bibtex" in args:
        print(bibtex())
    elif "--cff" in args:
        print(cff(), end="")
    elif "--sentence" in args:
        print(sentence())
    else:
        print(plain())
    return 0


if __name__ == "__main__":
    sys.exit(main())
