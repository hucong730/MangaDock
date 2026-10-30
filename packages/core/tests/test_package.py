import re

import mangadock_core
from mangadock_core import schemas


def test_package_exposes_version_and_schema_namespace() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", mangadock_core.__version__)
    assert schemas.__name__ == "mangadock_core.schemas"
