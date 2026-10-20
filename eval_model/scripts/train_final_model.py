"""
train_final_model.py
---------------------
compare_models.py 는 GroupKFold로 "성능을 검증"만 하고 모델을 저장하지 않는다.
이 스크립트는 검증에서 가장 좋았던 모델(RandomForest, pooled R² 0.616)을
36개 데이터 전체로 다시 학습해 실제 서비스에서 쓸 모델 파일로 저장한다.

산출물 (eval_model/models/):
  {item_key}.joblib      — 항목별 회귀 파이프라인 (SimpleImputer + RandomForestRegressor)
  feature_columns.json   — 학습에 쓴 feature 컬럼 순서 (추론 시 동일 순서로 맞춰야 함)
  targets.json           — 항목명 → (표시명, 채점표 가중치) 매핑 + 총점 계산 방식

실행:
  python3 train_final_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

BASE = Path("/workspace/CSM/eval_model")
DATA_CSV = BASE / "data" / "dataset.csv"
MODEL_DIR = BASE / "models"

# compare_models.py 와 동일 — 채점표 '모델학습용' 시트 컬럼 → (리포트 항목명, 가중치)
TARGETS = {
    "말속도":     ("발화속도", 15),
    "명확성":     ("말하기안정성", 15),
    "침묵":       ("유창성침묵", 15),
    "습관어":     ("습관어반복", 10),
    "시선비율":   ("시선처리", 15),
    "표정":       ("표정자연스러움", 15),
    "상반신자세": ("자세움직임", 15),
}
LABEL_COL = "label_score"
GROUP_COL = "group"
DROP_COLS = {"video_id", "class_dir", "elapsed_sec", "frames_sampled"}
RATER_SUBSCORES = list(TARGETS.keys())
SEED = 42


def build_model() -> Pipeline:
    """compare_models.py의 RandomForest baseline과 동일한 하이퍼파라미터."""
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(
            n_estimators=300, max_depth=4, min_samples_leaf=2,
            max_features="sqrt", random_state=SEED, n_jobs=2)),
    ])


def main():
    df = pd.read_csv(DATA_CSV)
    feature_cols = [c for c in df.columns
                    if c not in DROP_COLS | {LABEL_COL, GROUP_COL} | set(RATER_SUBSCORES)]

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    X = df[feature_cols]
    print(f"학습 데이터 {len(df)}행, feature {len(feature_cols)}개, 항목 {len(TARGETS)}개\n")

    for item_key, (report_name, weight) in TARGETS.items():
        y = df[item_key]
        pipe = build_model()
        pipe.fit(X, y)
        out_path = MODEL_DIR / f"{item_key}.joblib"
        joblib.dump(pipe, out_path)

        # 학습 데이터 자체에 대한 적합도(참고용 — 실제 성능은 compare_models.py의 CV 결과를 봐야 함)
        train_mae = (pipe.predict(X) - y).abs().mean()
        print(f"  {item_key:8s} → {report_name:10s} (가중치 {weight:2d}) "
              f"저장 완료, train MAE={train_mae:.3f} → {out_path.name}")

    (MODEL_DIR / "feature_columns.json").write_text(
        json.dumps(feature_cols, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "targets.json").write_text(
        json.dumps(
            {
                "targets": {k: {"report_name": v[0], "weight": v[1]} for k, v in TARGETS.items()},
                "score_scale": {"min": 1, "max": 5},
                "total_scale": {"min": 0, "max": 100},
                "note": "총점 = Σ ((항목점수 - score_scale.min) / (score_scale.max - score_scale.min)) * weight",
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nfeature_columns.json / targets.json 저장 완료 → {MODEL_DIR}")
    print("\n※ 이 모델들의 실제 일반화 성능은 compare_models.py의 GroupKFold 결과"
          "(results/model_results.csv, pooled_r2 ≈ 0.6)를 참고할 것 — "
          "여기서 찍은 train MAE는 과최적화된 값이라 참고용일 뿐임.")


if __name__ == "__main__":
    main()
