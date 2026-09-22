"""
extract_features.py 가 만든 영상별 JSON + labels.csv 를 합쳐 학습용 데이터셋을 만든다.
동시에 요청받은 데이터 점검 항목(개수/결측/범위/그룹/라벨분포)을 출력한다.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("/workspace/CSM/eval_model/data")
FEATURE_DIR = BASE / "features"
LABELS_CSV = BASE / "labels.csv"
OUT_CSV = BASE / "dataset.csv"

DROP_COLS = {"video_id", "class_dir", "video_path", "errors", "elapsed_sec", "frames_sampled"}
LABEL_COL = "label_score"
GROUP_COL = "group"
# 채점표의 사람이 매긴 세부점수 — 최종점수의 가중합 입력이라 feature로 쓰면 누수
RATER_SUBSCORES = ["말속도", "명확성", "침묵", "습관어", "시선비율", "표정", "상반신자세"]


def load_features() -> pd.DataFrame:
    rows = []
    for path in sorted(FEATURE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("errors"):
            print(f"[경고] {record['video_id']} 추출 오류: {record['errors']}")
        rows.append({k: v for k, v in record.items() if k not in {"errors", "video_path"}})
    return pd.DataFrame(rows)


def main():
    features = load_features()
    labels = pd.read_csv(LABELS_CSV)

    features["video_id"] = features["video_id"].str.strip()
    labels["video_id"] = labels["video_id"].str.strip()

    df = features.merge(labels, on="video_id", how="inner")
    print(f"feature {len(features)}행 + label {len(labels)}행 → merge {len(df)}행")

    unmatched = set(features["video_id"]) ^ set(labels["video_id"])
    if unmatched:
        print(f"[경고] 매칭 실패한 video_id: {sorted(unmatched)}")

    df = df[df[LABEL_COL].notna()].reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    feature_cols = [c for c in df.columns
                    if c not in DROP_COLS | {LABEL_COL, GROUP_COL} | set(RATER_SUBSCORES)]

    print("\n" + "=" * 70)
    print("데이터 점검")
    print("=" * 70)
    print(f"1. 전체 데이터 수      : {len(df)}")
    print(f"2. feature 개수        : {len(feature_cols)}")
    print(f"3. feature 이름        :")
    for i in range(0, len(feature_cols), 4):
        print("     " + ", ".join(feature_cols[i:i + 4]))

    label = df[LABEL_COL]
    print(f"\n4. label 형태          : {label.dtype}, 고유값 {label.nunique()}개 "
          f"→ {'연속형(regression)' if label.nunique() > 10 else '범주형 가능성'}")
    print(f"   label 분포          : min={label.min():.2f} q25={label.quantile(.25):.2f} "
          f"median={label.median():.2f} q75={label.quantile(.75):.2f} max={label.max():.2f} "
          f"mean={label.mean():.2f} std={label.std():.2f}")

    na = df[feature_cols].isna().sum()
    na = na[na > 0]
    print(f"\n5. 결측값              : {'없음' if na.empty else ''}")
    if not na.empty:
        for col, cnt in na.items():
            print(f"     {col}: {cnt}개")

    print("\n6. feature 값 범위")
    desc = df[feature_cols].describe().T[["min", "mean", "max", "std"]]
    print(desc.to_string(float_format=lambda x: f"{x:9.3f}"))

    print("\n7. 그룹(사람) 구성")
    counts = df[GROUP_COL].value_counts().sort_index()
    print(f"     고유 인원 {len(counts)}명, 1인당 영상 수: {counts.to_dict()}")
    print("     → 같은 사람의 영상이 여러 개이므로 GroupKFold 필수")

    print("\n9. 조건별(폴더) label 평균")
    print(df.groupby("class_dir")[LABEL_COL].agg(["count", "mean", "std"]).to_string())

    print(f"\n저장 완료 → {OUT_CSV}")


if __name__ == "__main__":
    main()
