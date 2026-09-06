"""English argparse-help catalog (HELP_* keys).

Split from the runtime catalog so the ~180 help strings do not swamp the
message list (spec D1's surface split). EN values are byte-exact.
"""
from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {}
