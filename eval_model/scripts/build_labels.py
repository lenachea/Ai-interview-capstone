"""
채점표(AI_모의면접_채점표.xlsx)의 '모델학습용' 시트를 읽어
video_id, group(사람), label(최종 100점 스코어), 세부 항목 평균을 labels.csv로 저장.
"""
import re
import openpyxl
import pandas as pd
from pathlib import Path

XLSX_PATH = "/workspace/AI_모의면접_채점표.xlsx"
OUT_PATH = "/workspace/CSM/eval_model/data/labels.csv"

SUBSCORE_COLS = ["말속도", "명확성", "침묵", "습관어", "시선비율", "표정", "상반신자세"]


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["모델학습용"]

    rows = []
    for r in range(4, ws.max_row + 1):
        video_id = ws.cell(row=r, column=1).value
        if not video_id:
            continue
        final_score = ws.cell(row=r, column=10).value
        subscores = [ws.cell(row=r, column=c).value for c in range(3, 10)]

        group = re.split(r"[_]", video_id.strip())[0]
        rows.append({
            "video_id": video_id,
            "group": group,
            **dict(zip(SUBSCORE_COLS, subscores)),
            "label_score": final_score,
        })

    df = pd.DataFrame(rows)
    missing = df[df["label_score"].isna()]
    if len(missing):
        print(f"[경고] label 누락 {len(missing)}건 (학습 대상에서 제외됨):")
        print(missing["video_id"].tolist())

    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n총 {len(df)}행 중 label 유효 {df['label_score'].notna().sum()}행 → {OUT_PATH}")
    print(df.head(10))


if __name__ == "__main__":
    main()
