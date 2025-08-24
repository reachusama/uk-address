"""
CRFsuite-based UK address parser with tagger caching and pluggable tokeniser.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Tuple

import pycrfsuite

from . import models as default_mod
from . import tokens as default_tok

MODEL_PATH = str(default_mod.resolve_model_path())


@lru_cache(maxsize=8)
def _get_tagger(model_path: str = MODEL_PATH) -> pycrfsuite.Tagger:
    tagger = pycrfsuite.Tagger()
    tagger.open(model_path)
    return tagger


def _parse(
    raw: str, model_path: str = MODEL_PATH, tok=default_tok
) -> Tuple[List[str], List[str]]:
    tokens: List[str] = tok.tokenize(raw)
    if not tokens:
        return [], []
    features = tok.tokens2features(tokens)
    if not features:
        return tokens, []
    tags: List[str] = _get_tagger(model_path).tag(features)
    return tokens, tags


def parse(
    raw: str, model_path: str = MODEL_PATH, tok=default_tok
) -> List[Tuple[str, str]]:
    tokens, tags = _parse(raw, model_path, tok)
    if not tokens or not tags:
        return []
    return list(zip(tokens, tags))


def parse_with_marginal_probability(
    raw: str, model_path: str = MODEL_PATH, tok=default_tok
):
    tokens, tags = _parse(raw, model_path, tok)
    if not tokens or not tags:
        return []
    tagger = _get_tagger(model_path)
    marginals = [tagger.marginal(tag, i) for i, tag in enumerate(tags)]
    return list(zip(tokens, tags, marginals))


def parse_with_probabilities(
    raw: str, model_path: str = MODEL_PATH, tok=default_tok
) -> Dict[str, Any]:
    tokens, tags = _parse(raw, model_path, tok)
    if not tokens or not tags:
        return {
            "tokens": [],
            "tags": [],
            "marginal_probabilities": [],
            "sequence_probability": 0.0,
        }
    tagger = _get_tagger(model_path)
    marginals = [tagger.marginal(tag, i) for i, tag in enumerate(tags)]
    seq_p = tagger.probability(tags)
    return {
        "tokens": tokens,
        "tags": tags,
        "marginal_probabilities": marginals,
        "sequence_probability": seq_p,
    }


def tag(raw: str, model_path: str = MODEL_PATH, tok=default_tok) -> Dict[str, str]:
    out: Dict[str, List[str]] = {}
    for token, label in parse(raw, model_path, tok):
        out.setdefault(label, []).append(token)
    return {label: " ".join(parts).strip(" ,;") for label, parts in out.items()}
