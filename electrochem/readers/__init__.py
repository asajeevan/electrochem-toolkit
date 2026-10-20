"""Reading cycling data from instruments other than BioLogic.

What is true: every cycler on the market exports delimited text or a spreadsheet,
and one generic reader (reader.py) handles any such export once it knows four
things no file states about itself: the sign convention of the current, where
the direction comes from, what the capacity columns accumulate, and the cycle
numbering base. Those live in a typed profile (profile.py) that cannot be built
without them.

What is not claimed: that every cycler is recognised out of the box. Built-in
profiles (builtin.py) exist for instruments whose real export files were read
and checked; any other instrument is learned once, from one of its files, through
the proposer (propose.py) and the import review step in the window, and saved to
the registry (registry.py) against a fingerprint of its header. Every later file
from that instrument is then recognised automatically.

The validated EC-Lab path (eclab_import) is never routed through here: bridge.is_eclab
decides from the file's own signature.
"""
from .bridge import is_eclab, to_table
from .builtin import BUILTIN
from .profile import Binding, Conventions, ImportProfile, Layout
from .propose import Proposal, looks_tabular
from .propose import propose as propose_mapping
from .reader import ImportFailure, RawTable, read
from .registry import Entry, Registry, confirm, fingerprint

__all__ = ["BUILTIN", "Binding", "Conventions", "Entry", "ImportFailure", "ImportProfile", "Layout", "Proposal",
           "RawTable", "Registry", "confirm", "fingerprint", "is_eclab", "looks_tabular", "propose_mapping", "read",
           "to_table"]
