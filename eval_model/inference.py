"""
inference.py
-------------
scripts/train_final_model.py 가 저장한 모델들을 불러와, 영상 한 편에서 뽑은
raw feature dict(nonverbal_module/vision_features.py + 언어 feature 어댑터)로부터
채점표 7개 항목(1~5점)과 총점(0~100점)을 예측한다.

backend/main.py 에서:
    from eval_model.inference import predict_scores
    result = predict_scores(feature_dict)   # {"말속도": 4.2, ..., "총점": 81.3}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "models"

_models: dict = {}
_feature_columns: Optional[list] = None
_targets: Optional[dict] = None


def _load():
    global _feature_columns, _targets
    if _feature_columns is not None:
        return

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"{MODEL_DIR} 없음 — 먼저 eval_model/scripts/train_final_model.py 를 실행해서 "
            "모델을 학습/저장해야 합니다."
        )

    _feature_columns = json.loads((MODEL_DIR / "feature_columns.json").read_text(encoding="utf-8"))
    _targets = json.loads((MODEL_DIR / "targets.json").read_text(encoding="utf-8"))

    for item_key in _targets["targets"]:
        model_path = MODEL_DIR / f"{item_key}.joblib"
        if not model_path.exists():
            raise FileNotFoundError(f"모델 파일 없음: {model_path}")
        _models[item_key] = joblib.load(model_path)


def is_ready() -> bool:
    """모델 파일이 저장돼 있는지 확인 (호출 전에 체크용)."""
    return (MODEL_DIR / "feature_columns.json").exists()


def predict_scores(features: dict) -> dict:
    """
    Parameters
    ----------
    features : dict
        feature_columns.json 에 있는 컬럼들을 key로 갖는 dict.
        일부가 없거나 None/NaN이어도 됨 (학습 때와 동일하게 median imputation).

    Returns
    -------
    {
        "말속도": 4.2, "명확성": 3.8, "침묵": 4.0, "습관어": 3.5,
        "시선비율": 4.1, "표정": 3.9, "상반신자세": 4.3,
        "총점": 81.3,
        "items": {
            "말속도": {"report_name": "발화속도", "score_1to5": 4.2, "score_0to100": 80.0, "weight": 15},
            ...
        },
    }
    """
    _load()

    row = {col: features.get(col) for col in _feature_columns}
    X = pd.DataFrame([row], columns=_feature_columns)
    # 결측/NaN 문자열 등을 확실히 NaN으로 통일 (Pipeline의 SimpleImputer가 처리)
    X = X.apply(pd.to_numeric, errors="coerce")

    lo, hi = _targets["score_scale"]["min"], _targets["score_scale"]["max"]
    total_lo, total_hi = _targets["total_scale"]["min"], _targets["total_scale"]["max"]

    result: dict = {}
    items: dict = {}
    total = 0.0

    for item_key, meta in _targets["targets"].items():
        pred = float(_models[item_key].predict(X)[0])
        pred = float(np.clip(pred, lo, hi))
        pred_100 = (pred - lo) / (hi - lo) * (total_hi - total_lo) + total_lo

        result[item_key] = round(pred, 2)
        items[item_key] = {
            "report_name": meta["report_name"],
            "score_1to5": round(pred, 2),
            "score_0to100": round(pred_100, 1),
            "weight": meta["weight"],
        }
        total += pred_100 * meta["weight"] / 100.0

    result["총점"] = round(total, 2)
    result["items"] = items
    return result
