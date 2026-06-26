"""Config pytest condivisa.

La sola presenza di questo file alla radice del repo fa aggiungere a pytest la root
al sys.path, cosi' i test in tests/ possono `import tools` / `import agent` / `import storage`.
"""
import pytest

import storage


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Ogni test gira su un DB SQLite temporaneo e pulito (isolamento totale)."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.db"))
    storage.init_db()
    yield
