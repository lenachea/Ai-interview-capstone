"""
평가모델 baseline 비교: RandomForest vs Ridge vs XGBoost

구조 (실제 시스템 리포트와 동일):
    영상에서 뽑은 객관적 지표(X)
      → 채점표 7개 항목 점수(1~5)를 각각 예측
      → 채점표 수식으로 가중합하여 총점(0~100) 산출

검증:
  - 같은 사람이 여러 영상을 찍었으므로 GroupKFold(5), group=사람 (누수 방지)
  - 모든 모델이 동일 feature / 동일 preprocessing / 동일 fold 에서 비교됨
  - Ridge만 StandardScaler 필요 → Pipeline으로 fold 내부에서만 fit
  - 결측은 모든 모델 공통 median imputation (Pipeline 내부)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV
from xgboost import XGBRegressor

BASE = Path("/workspace/CSM/eval_model")
DATA_CSV = BASE / "data" / "dataset.csv"
RESULT_DIR = BASE / "results"

# 채점표 '모델학습용' 시트 컬럼 → (리포트 항목명, 가중치)
# 총점 = Σ ((항목점수 - 1) / 4) * 가중치   ← 채점표 Q열 수식과 동일
TARGETS = {
    "말속도":     ("발화속도", 15),
    "명확성":     ("말하기안정성", 15),
    "침묵":       ("유창성침묵", 15),
    "습관어":     ("습관어반복", 10),
    "시선비율":   ("시선처리", 15),
    "표정":       ("표정자연스러움", 15),
    "상반신자세": ("자세움직임", 15),
}
TOTAL_COL = "label_score"
GROUP_COL = "group"
DROP_COLS = {"video_id", "class_dir", "elapsed_sec", "frames_sampled"}
N_SPLITS = 5
SEED = 42


def build_models() -> dict:
    """33개 수준의 소규모 데이터라 baseline은 의도적으로 단순하게 설정."""
    return {
        "Dummy(mean)": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", DummyRegressor(strategy="mean")),
        ]),
        "RandomForest": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=300, max_depth=4, min_samples_leaf=2,
                max_features="sqrt", random_state=SEED, n_jobs=2)),
        ]),
        "Ridge": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0, 1000.0])),
        ]),
        "XGBoost": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", XGBRegressor(
                n_estimators=200, max_depth=2, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
                random_state=SEED, n_jobs=2, verbosity=0)),
        ]),
    }


def metrics(y_true, y_pred) -> dict:
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
    }


def to_total(item_scores: np.ndarray) -> np.ndarray:
    """항목점수(n, 7) → 총점(n,). 채점표 수식과 동일."""
    weights = np.array([w for _, w in TARGETS.values()], dtype=float)
    clipped = np.clip(item_scores, 1.0, 5.0)
    return ((clipped - 1.0) / 4.0 * weights).sum(axis=1)


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)

    target_cols = list(TARGETS)
    feature_cols = [c for c in df.columns
                    if c not in DROP_COLS | {TOTAL_COL, GROUP_COL} | set(target_cols)]
    X = df[feature_cols]
    Y = df[target_cols].to_numpy(dtype=float)
    y_total = df[TOTAL_COL].to_numpy(dtype=float)
    groups = df[GROUP_COL].to_numpy()

    print(f"데이터 {len(df)}행 / feature {len(feature_cols)}개 / "
          f"target {len(target_cols)}개 항목 / 그룹(사람) {len(set(groups))}명")
    print(f"GroupKFold(n_splits={N_SPLITS}) — 같은 사람이 train/val 양쪽에 들어가지 않음\n")

    folds = list(GroupKFold(n_splits=N_SPLITS).split(X, y_total, groups))
    for i, (tr, va) in enumerate(folds, 1):
        print(f"  fold{i}: train {len(tr)} / val {len(va)}  (val 인원: {sorted(set(groups[va]))})")
    print()

    model_names = list(build_models())
    item_rows, total_fold_rows, importance_rows = [], [], []
    oof_items = {n: np.full(Y.shape, np.nan) for n in model_names}

    for name in model_names:
        for fold_idx, (tr, va) in enumerate(folds, 1):
            for t_idx, col in enumerate(target_cols):
                model = build_models()[name]
                model.fit(X.iloc[tr], Y[tr, t_idx])

                pred_va = model.predict(X.iloc[va])
                pred_tr = model.predict(X.iloc[tr])
                oof_items[name][va, t_idx] = pred_va

                m_va, m_tr = metrics(Y[va, t_idx], pred_va), metrics(Y[tr, t_idx], pred_tr)
                item_rows.append({
                    "model": name, "fold": fold_idx,
                    "item": TARGETS[col][0], "item_col": col,
                    **{f"val_{k}": v for k, v in m_va.items()},
                    **{f"train_{k}": v for k, v in m_tr.items()},
                })

                est = model.named_steps["model"]
                if hasattr(est, "feature_importances_"):
                    for f_col, imp in zip(feature_cols, est.feature_importances_):
                        importance_rows.append({"model": name, "item": TARGETS[col][0],
                                                "feature": f_col, "importance": float(imp)})
                elif hasattr(est, "coef_"):
                    # StandardScaler 뒤라 계수 크기를 그대로 중요도로 볼 수 있다
                    for f_col, coef in zip(feature_cols, np.ravel(est.coef_)):
                        importance_rows.append({"model": name, "item": TARGETS[col][0],
                                                "feature": f_col, "importance": abs(float(coef)),
                                                "coef": float(coef)})

            pred_total_va = to_total(oof_items[name][va])
            total_fold_rows.append({
                "model": name, "fold": fold_idx, "n_train": len(tr), "n_val": len(va),
                **metrics(y_total[va], pred_total_va),
            })

    item_df = pd.DataFrame(item_rows)
    total_df = pd.DataFrame(total_fold_rows)
    imp_df = (pd.DataFrame(importance_rows)
              .groupby(["model", "item", "feature"])["importance"].mean().reset_index())

    # ── 요약 ────────────────────────────────────────────────────────────────
    summary_rows = []
    for name in model_names:
        sub = total_df[total_df.model == name]
        row = {"model": name}
        for metric in ("MAE", "RMSE", "R2"):
            row[f"{metric.lower()}_mean"] = float(sub[metric].mean())
            row[f"{metric.lower()}_std"] = float(sub[metric].std(ddof=0))
        pooled = metrics(y_total, to_total(oof_items[name]))
        row.update({f"pooled_{k.lower()}": v for k, v in pooled.items()})
        item_sub = item_df[item_df.model == name]
        row["item_mae_mean"] = float(item_sub.val_MAE.mean())
        row["overfit_gap_mae"] = float(item_sub.val_MAE.mean() - item_sub.train_MAE.mean())
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows).sort_values("mae_mean")

    item_summary = (item_df.groupby(["model", "item"])
                    .agg(val_MAE_mean=("val_MAE", "mean"), val_MAE_std=("val_MAE", "std"),
                         val_R2_mean=("val_R2", "mean"), train_MAE_mean=("train_MAE", "mean"))
                    .reset_index())

    RESULT_DIR.mkdir(exist_ok=True)
    item_df.to_csv(RESULT_DIR / "item_fold_results.csv", index=False, encoding="utf-8-sig")
    item_summary.to_csv(RESULT_DIR / "item_results.csv", index=False, encoding="utf-8-sig")
    total_df.to_csv(RESULT_DIR / "fold_results.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(RESULT_DIR / "model_results.csv", index=False, encoding="utf-8-sig")
    imp_df.sort_values(["model", "item", "importance"], ascending=[True, True, False]).to_csv(
        RESULT_DIR / "feature_importance.csv", index=False, encoding="utf-8-sig")

    oof_frames = []
    for name in model_names:
        frame = pd.DataFrame(oof_items[name], columns=[f"pred_{TARGETS[c][0]}" for c in target_cols])
        frame.insert(0, "model", name)
        frame.insert(0, "video_id", df["video_id"])
        frame["pred_total"] = to_total(oof_items[name])
        frame["true_total"] = y_total
        for c in target_cols:
            frame[f"true_{TARGETS[c][0]}"] = df[c]
        oof_frames.append(frame)
    pd.concat(oof_frames).to_csv(RESULT_DIR / "oof_predictions.csv", index=False, encoding="utf-8-sig")

    (RESULT_DIR / "results.json").write_text(json.dumps({
        "n_samples": len(df), "n_features": len(feature_cols),
        "n_groups": int(len(set(groups))), "cv": f"GroupKFold({N_SPLITS})",
        "targets": {c: {"item": TARGETS[c][0], "weight": TARGETS[c][1]} for c in target_cols},
        "total_formula": "sum((item_score - 1) / 4 * weight)",
        "feature_names": feature_cols,
        "summary_total": summary_rows,
        "item_summary": item_summary.to_dict("records"),
        "total_folds": total_fold_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 출력 ────────────────────────────────────────────────────────────────
    for name in model_names:
        print("=" * 70)
        print(f"Model: {name}   — 총점(0~100) 예측 성능")
        sub = total_df[total_df.model == name]
        for metric in ("MAE", "RMSE", "R2"):
            print(f"\n  {metric}")
            for _, r in sub.iterrows():
                print(f"    Fold {int(r['fold'])}: {r[metric]:8.3f}")
            print(f"    Mean ± Std: {sub[metric].mean():.3f} ± {sub[metric].std(ddof=0):.3f}")
        print()

    print("=" * 70)
    print("총점 기준 모델 비교 (pooled = out-of-fold 전체 예측)")
    print("=" * 70)
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:8.3f}"))

    print("\n" + "=" * 70)
    print("항목별 점수(1~5) 예측 MAE — 모델 × 항목")
    print("=" * 70)
    pivot = item_summary.pivot(index="item", columns="model", values="val_MAE_mean")
    print(pivot.to_string(float_format=lambda x: f"{x:7.3f}"))

    print("\n" + "=" * 70)
    print("Feature importance — 항목별 상위 5개 (RandomForest 기준)")
    print("=" * 70)
    rf_imp = imp_df[imp_df.model == "RandomForest"]
    for _, item in TARGETS.items():
        sub = rf_imp[rf_imp.item == item[0]].nlargest(5, "importance")
        print(f"\n[{item[0]}] (가중치 {item[1]})")
        for _, r in sub.iterrows():
            print(f"    {r['feature']:<28} {r['importance']:.4f}")

    print(f"\n결과 저장 → {RESULT_DIR}")


if __name__ == "__main__":
    main()
