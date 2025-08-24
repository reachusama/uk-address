"""
Model management:
- resolve_model_path(): discovery order (explicit/env/config/cache default/packaged baseline)
- download_model(): downloads to user cache with optional sha256
- list_installed_models(), set_default_model()
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import List, Optional

from platformdirs import user_cache_dir, user_config_dir

PKG = "ukaddresskit"
APP = "ukaddresskit"

CONFIG_DIR = Path(user_config_dir(APP))
CACHE_DIR = Path(user_cache_dir(APP))
MODELS_DIR = CACHE_DIR / "models"
DEFAULT_PTR = MODELS_DIR / "default.txt"
CONFIG_FILE = CONFIG_DIR / "config.json"
BASELINE_RESOURCE = "data/models/base.crfsuite"


@dataclass
class ModelInfo:
    name: str
    path: Path


def _ensure_dirs():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _read_config_model_path() -> Optional[Path]:
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            p = Path(data.get("model_path", "")).expanduser()
            return p if p.is_file() else None
    except Exception:
        return None
    return None


def _write_default_pointer(p: Path) -> None:
    DEFAULT_PTR.write_text(p.name)


def _read_default_pointer() -> Optional[Path]:
    if DEFAULT_PTR.exists():
        p = (MODELS_DIR / DEFAULT_PTR.read_text().strip()).expanduser()
        return p if p.is_file() else None
    return None


def _baseline_as_file() -> Optional[Path]:
    ref = resources.files(PKG).joinpath(BASELINE_RESOURCE)
    if not ref.exists():
        return None
    with resources.as_file(ref) as fs_path:
        return Path(fs_path)


def list_installed_models() -> List[ModelInfo]:
    _ensure_dirs()
    out: List[ModelInfo] = []
    if MODELS_DIR.is_dir():
        for f in MODELS_DIR.glob("*.crfsuite"):
            out.append(ModelInfo(name=f.stem, path=f))
    return out


def set_default_model(path_or_name: str) -> Path:
    _ensure_dirs()
    candidate = Path(path_or_name).expanduser()
    if candidate.is_file():
        _write_default_pointer(candidate)
        return candidate
    candidate = MODELS_DIR / f"{path_or_name}.crfsuite"
    if candidate.is_file():
        _write_default_pointer(candidate)
        return candidate
    raise FileNotFoundError(f"Model not found: {path_or_name}")


def resolve_model_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Explicit model path not found: {explicit}")
    env = os.getenv("UKADDRESS_MODEL")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    p = _read_config_model_path()
    if p:
        return p
    p = _read_default_pointer()
    if p:
        return p
    p = _baseline_as_file()
    if p:
        return p
    raise FileNotFoundError(
        "No model found. Put a model at ~/.cache/ukaddresskit/models, set UKADDRESS_MODEL, "
        "or add a packaged baseline at src/uk-address/data/models/base.crfsuite. "
        "You can also run: ukaddresskit models download <name> <url> --sha256 <hash>"
    )


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_model(
    name: str, url: str, sha256: Optional[str] = None, make_default: bool = True
) -> Path:
    _ensure_dirs()
    dest = MODELS_DIR / f"{name}.crfsuite"
    tmp = dest.with_suffix(".tmp")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as out:
        shutil.copyfileobj(r, out)
    if sha256:
        got = _sha256_of(tmp)
        if got.lower() != sha256.lower():
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"SHA256 mismatch for {name}: expected {sha256}, got {got}"
            )
    tmp.replace(dest)
    if make_default:
        _write_default_pointer(dest)
    return dest
