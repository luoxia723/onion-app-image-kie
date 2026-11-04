"""Active font samples for new choices; originals remain usable by frozen jobs."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def disabled_names():
    config=ROOT/'config/font-library.json'
    return set(json.loads(config.read_text(encoding='utf-8')).get('disabled_files',{})) if config.exists() else set()


def font_references(directory=None, *, include_disabled=False):
    directory=Path(directory) if directory is not None else ROOT/'assets/font-references'
    disabled=set() if include_disabled else disabled_names()
    return [path for path in sorted(directory.glob('*.png')) if path.name not in disabled]
