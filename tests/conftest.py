import os
import re
import tempfile
import uuid
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_TMP_DIR = Path(__file__).parents[1] / ".tmp" / "pytest"
TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEST_TMP_DIR)
os.environ["TMP"] = str(TEST_TMP_DIR)
os.environ["TEMP"] = str(TEST_TMP_DIR)
os.environ["TMPDIR"] = str(TEST_TMP_DIR)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def local_tmp_path(request) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)
    path = TEST_TMP_DIR / f"{safe_name}-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path
