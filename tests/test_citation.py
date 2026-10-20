"""The citation: one source, four forms, and the committed CITATION.cff is the generated one."""
import re
from pathlib import Path

from electrochem import __released__, __url__, __version__, citation

ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_citation_file_is_the_generated_one():
    """A version bump without `python -m electrochem.citation --write` would leave GitHub's 'Cite this
    repository' box on the old version; this test makes that impossible to miss."""
    assert (ROOT / "CITATION.cff").read_text(encoding="utf-8") == citation.cff()


def test_every_form_carries_the_version_the_year_the_author_and_the_url():
    year = __released__[:4]
    for name, text in citation.all_forms().items():
        assert __version__ in text, name
        assert year in text, name
        assert citation.FAMILY in text, name
        assert __url__ in text, name


def test_bibtex_entry_is_well_formed_and_keeps_the_two_word_family_name():
    b = citation.bibtex()
    assert b.startswith("@software{cyclara_") and b.rstrip().endswith("}")
    fields = dict(re.findall(r"^\s*(\w+)\s*=\s*\{(.*)\},?$", b, flags=re.M))
    assert fields["author"] == "{Shyma Sajeevan}, Aswadh"       # braces: BibTeX must not split the family name
    assert fields["version"] == __version__ and fields["year"] == __released__[:4]
    assert fields["url"] == __url__ and fields["license"] == "GPL-3.0-or-later"
    assert b.count("{") == b.count("}")


def test_cff_has_the_required_keys_and_a_valid_date():
    text = citation.cff()
    for key in ("cff-version: 1.2.0", "message:", "title:", "authors:", "family-names:", "given-names:",
                f"version: {__version__}", f"date-released: {__released__}", "license: GPL-3.0-or-later"):
        assert key in text, key
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", __released__)


def test_the_release_date_belongs_to_this_version_not_an_older_one():
    """pyproject and the package agree on the version, and the date is not before the first release."""
    import tomllib
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert py["project"]["version"] == __version__
    assert __released__ >= "2026-09-01"


def test_the_command_line_prints_the_citation(capsys):
    from electrochem.analyze import main
    assert main(["--cite"]) == 0
    assert capsys.readouterr().out.strip() == citation.plain()
    assert main(["--cite", "--bibtex"]) == 0
    assert capsys.readouterr().out.strip() == citation.bibtex()
