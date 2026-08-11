"""Shared test setup.

The package is installed in editable mode (`pip install -e .`), so tests import
`qbi_pipeline` normally. No sys.path manipulation needed -- that was a Phase 0
stopgap for the old flat layout.
"""

import pytest

from qbi_pipeline.naming import DISPLAY_NAMES


@pytest.fixture(autouse=True)
def isolated_display_names():
    """Display-name overrides come from the build config and are process-global.

    Restored around every test so one test configuring them cannot change what
    another test's titles look like.
    """
    saved = dict(DISPLAY_NAMES)
    DISPLAY_NAMES.clear()
    yield DISPLAY_NAMES
    DISPLAY_NAMES.clear()
    DISPLAY_NAMES.update(saved)
