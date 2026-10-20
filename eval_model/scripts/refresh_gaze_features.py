"""
refresh_gaze_features.py
-------------------------
시선 분석을 MediaPipe blendshape → L2CS-Net(yaw/pitch 회귀 + 영상별 baseline 보정)으로
교체한 뒤, 기존 36개 feature json의 gaze_*/emo_* 필드만 다시 뽑아 갱신한다.
언어(STT)/자세(posture_rtmpose_3d) feature는 이 교체와 무관하므로 건드리지 않는다.

실행:
  LD_LIBRARY_PATH=/opt/conda/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/conda/lib \
      python3 refresh_gaze_features.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

CSM_DIR = Path("/workspace/CSM")
FEATURE_DIR = CSM_DIR / "eval_model" / "data" / "features"
VIDEO_DIR = CSM_DIR / "eval_model" / "data" / "raw_videos"

sys.path.append(str(CSM_DIR / "nonverbal_module"))

from vision_features import extract_gaze_emotion  # noqa: E402


def video_list():
    items = []
    for cls_dir in sorted(VIDEO_DIR.iterdir()):
        if cls_dir.is_dir():
            for video in sorted(cls_dir.glob("*.mp4")):
                items.append((video.stem, video))
    return items


def main():
    videos = {vid: path for vid, path in video_list()}
    feature_files = sorted(FEATURE_DIR.glob("*.json"))
    print(f"대상 {len(feature_files)}개\n")

    for i, fpath in enumerate(feature_files, 1):
        video_id = fpath.stem
        video_path = videos.get(video_id)
        if video_path is None:
            print(f"[{i}/{len(feature_files)}] {video_id} — 원본 영상 못 찾음, 건너뜀")
            continue

        print(f"[{i}/{len(feature_files)}] {video_id} 처리 중...", flush=True)
        t0 = time.time()
        try:
            new_gaze = extract_gaze_emotion(str(video_path), sample_fps=2.0, device="cuda")
            new_gaze.pop("_gaze_summary", None)
            new_gaze.pop("_emotion_counts", None)
            new_gaze.pop("_expression_deductions", None)
        except Exception as e:
            print(f"    실패: {e}")
            continue

        record = json.loads(fpath.read_text(encoding="utf-8"))
        record.update(new_gaze)
        fpath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    완료 ({time.time()-t0:.1f}s) gaze_center_ratio={new_gaze.get('gaze_center_ratio')}")

    print("\n전체 완료")


if __name__ == "__main__":
    main()
