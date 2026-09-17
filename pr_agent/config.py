import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KNOWLEDGE = ROOT / "knowledge"
load_dotenv(ROOT / ".env")


def _load_yaml(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


SETTINGS = _load_yaml("settings.yaml")
AUDIENCES = _load_yaml("audiences.yaml")
MODEL = os.getenv("PR_AGENT_MODEL") or SETTINGS.get("model", "claude-sonnet-5")
