"""
Fails CI if domain/ or application/ import a restricted (SDK/framework)
package directly. Domain and application code must depend only on
domain.ports abstractions — concrete SDKs belong in infrastructure/.
"""

import ast
from pathlib import Path

import pytest

RESTRICTED_IMPORTS = {
    "openai",
    "ollama",
    "anthropic",
    "fastapi",
    "sqlalchemy",
    "psycopg2",
    "psycopg",
    "requests",
    "httpx",
}

RESTRICTED_ROOTS = ["domain", "application"]

def _iter_py_files():
    for root in RESTRICTED_ROOTS:
        yield from Path(root).rglob("*.py")


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("path", list(_iter_py_files()), ids=lambda p: str(p))
def test_no_restricted_imports(path: Path):
    found = _imports_in(path) & RESTRICTED_IMPORTS
    assert not found, f"{path} imports restricted package(s): {found}"