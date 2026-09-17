from .config import KNOWLEDGE


def _read(name, drop_todo=True):
    path = KNOWLEDGE / name
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    if drop_todo:
        lines = [l for l in lines if "TODO" not in l]
    return "\n".join(lines).strip()


def facts():
    """Everything in knowledge/ except the voice file, with TODO lines removed."""
    parts = [_read(p.name) for p in sorted(KNOWLEDGE.glob("*.md")) if p.name != "voice.md"]
    return "\n\n".join(p for p in parts if p)


def voice():
    return _read("voice.md", drop_todo=False)
