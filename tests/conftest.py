import pytest

from pr_agent import tracker


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Point the tracker at a throwaway pipeline so tests never touch data/."""
    monkeypatch.setattr(tracker, "DATA", tmp_path)
    monkeypatch.setattr(tracker, "PIPELINE", tmp_path / "pipeline.csv")
    return tmp_path


def write_csv(path, *rows):
    header = "name,email,organisation,role,audience,website,source,notes\n"
    path.write_text(header + "".join(r.rstrip("\n") + "\n" for r in rows), encoding="utf-8")
    return path
