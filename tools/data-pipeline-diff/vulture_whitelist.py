"""Vulture whitelist for data_pipeline_diff.py.

Lists names that appear unused to vulture but are actually live code:
row_factory is set on sqlite3 connection and used implicitly
when iterating cursor results with row_factory=sqlite3.Row.
"""

# pylint: disable=pointless-statement
# Pointless statements are intentional here to serve as a Vulture whitelist.


import sqlite3  # noqa: F401

sqlite3.Row  # noqa: F821
sqlite3.Connection.row_factory  # noqa: F821

# Also reference the attribute in context
_conn = sqlite3.connect(":memory:")  # noqa: F821
_conn.row_factory  # noqa: F821
