import os
from collections import deque
from dataclasses import dataclass
from typing import Optional, List

import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


_DEFAULT_MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "pose_landmarker.task",
)

LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12


def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) / 2.0


@dataclass
class PostureMetrics:
    shoulder_tilt: float
    shoulder_elevation: float
    visible: bool = True

    def as_dict(self) -> dict:
        return {
            "shoulder_tilt": round(self.shoulder_tilt, 4),
            "shoulder_elevation": round(self.shoulder_elevation, 4),
            "visible": self.visible,
        }


@dataclass
class PostureConfig:
    shoulder_tilt_delta: float = 0.06
    shoulder_elevation_delta: float = 0.07

    shoulder_tilt_abs: float = 0.12
    shoulder_elevation_abs: float = 0.25

    min_visibility: float = 0.5
    smoothing_window: int = 3


class PostureAnalyzer:

    def __init__(self, config: Optional[PostureConfig] = None, model_path: Optional[str] = None):
        self.cfg = config or PostureConfig()

        path = model_path or _DEFAULT_MODEL
        if not os.path.exists(path):
            raise FileNotFoundError(f"pose_landmarker.task 모델 파일을 찾을 수 없습니다: {path}")

        with open(path, "rb") as f:
            model_data = f.read()
        base_options = mp_python.BaseOptions(model_asset_buffer=model_data)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        self._calib_buffer: List[PostureMetrics] = []
        self.baseline: Optional[PostureMetrics] = None
        self._label_buffer: deque = deque(maxlen=self.cfg.smoothing_window)

    def _extract_metrics(self, frame_rgb: np.ndarray) -> Optional[PostureMetrics]:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect(mp_image)

        if not result.pose_landmarks:
            return None

        lm = result.pose_landmarks[0]
        h, w = frame_rgb.shape[:2]

        def pt(idx):
            p = lm[idx]
            return np.array([p.x * w, p.y * h]), p.visibility if p.visibility is not None else 1.0

        (l_ear, v1), (r_ear, v2) = pt(LEFT_EAR), pt(RIGHT_EAR)
        (l_sh, v3), (r_sh, v4) = pt(LEFT_SHOULDER), pt(RIGHT_SHOULDER)

        visible = min(v1, v2, v3, v4) >= self.cfg.min_visibility

        shoulder_width = np.linalg.norm(l_sh - r_sh)
        if shoulder_width < 1e-3:
            return None

        ear_mid = _midpoint(l_ear, r_ear)
        sh_mid = _midpoint(l_sh, r_sh)

        shoulder_tilt = abs(l_sh[1] - r_sh[1]) / shoulder_width
        shoulder_elevation = (sh_mid[1] - ear_mid[1]) / shoulder_width

        return PostureMetrics(
            shoulder_tilt=shoulder_tilt,
            shoulder_elevation=shoulder_elevation,
            visible=visible,
        )

    def feed_calibration(self, frame_rgb: np.ndarray) -> bool:
        m = self._extract_metrics(frame_rgb)
        if m is not None and m.visible:
            self._calib_buffer.append(m)
            return True
        return False

    def finalize_calibration(self) -> bool:
        if len(self._calib_buffer) < 3:
            self.baseline = None
            return False
        self.baseline = PostureMetrics(
            shoulder_tilt=float(np.median([m.shoulder_tilt for m in self._calib_buffer])),
            shoulder_elevation=float(np.median([m.shoulder_elevation for m in self._calib_buffer])),
        )
        self._calib_buffer.clear()
        return True

    def _classify(self, m: PostureMetrics) -> tuple:
        cfg = self.cfg

        if self.baseline is not None:
            d_tilt = m.shoulder_tilt - self.baseline.shoulder_tilt
            d_elev = m.shoulder_elevation - self.baseline.shoulder_elevation

            tilt_bad = abs(d_tilt) > cfg.shoulder_tilt_delta
            elev_bad = d_elev < -cfg.shoulder_elevation_delta

            max_ratio = max(
                abs(d_tilt) / cfg.shoulder_tilt_delta,
                max(0.0, -d_elev / cfg.shoulder_elevation_delta),
            )
            deviation = {
                "shoulder_tilt": round(d_tilt, 4),
                "shoulder_elevation": round(d_elev, 4),
            }
        else:
            tilt_bad = m.shoulder_tilt > cfg.shoulder_tilt_abs
            elev_bad = m.shoulder_elevation < cfg.shoulder_elevation_abs

            max_ratio = max(
                m.shoulder_tilt / cfg.shoulder_tilt_abs,
                max(0.0, (cfg.shoulder_elevation_abs - m.shoulder_elevation) / cfg.shoulder_elevation_abs),
            )
            deviation = {}

        is_slouched = tilt_bad or elev_bad
        clamped = float(np.clip(max_ratio, 0.0, 1.0))
        confidence = clamped if is_slouched else float(np.clip(1.0 - clamped, 0.0, 1.0))

        return is_slouched, deviation, confidence

    def analyze(self, frame_rgb: np.ndarray) -> dict:
        m = self._extract_metrics(frame_rgb)

        if m is None or not m.visible:
            return {
                "label": "unknown",
                "metrics": m.as_dict() if m else None,
                "deviation": {},
                "confidence": 0.0,
                "raw_label": "unknown",
            }

        is_slouched, deviation, confidence = self._classify(m)
        raw_label = "slouched" if is_slouched else "upright"

        self._label_buffer.append(1 if is_slouched else 0)
        vote = sum(self._label_buffer) / len(self._label_buffer)
        smoothed = "slouched" if vote >= 0.5 else "upright"

        return {
            "label": smoothed,
            "metrics": m.as_dict(),
            "deviation": deviation,
            "confidence": round(confidence, 3),
            "raw_label": raw_label,
        }

    def reset_smoothing(self):
        self._label_buffer.clear()

    def close(self):
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _draw_overlay(frame_bgr: np.ndarray, result: dict, lm_pts: dict) -> np.ndarray:
    vis = frame_bgr.copy()
    label = result["label"]
    dev = result.get("deviation", {})
    m = result.get("metrics", {}) or {}

    SLOUCH_C = (0, 0, 220)
    UPRIGHT_C = (0, 190, 0)
    UNKNOWN_C = (120, 120, 120)
    main_color = SLOUCH_C if label == "slouched" else UPRIGHT_C if label == "upright" else UNKNOWN_C

    if lm_pts:
        l_ear, r_ear = lm_pts["l_ear"], lm_pts["r_ear"]
        l_sh, r_sh = lm_pts["l_sh"], lm_pts["r_sh"]
        ear_mid = ((l_ear[0] + r_ear[0]) // 2, (l_ear[1] + r_ear[1]) // 2)
        sh_mid = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2)

        tilt_bad = abs(dev.get("shoulder_tilt", 0)) > 0.06
        cv2.line(vis, l_sh, r_sh, SLOUCH_C if tilt_bad else UPRIGHT_C, 3)

        elev_bad = dev.get("shoulder_elevation", 0) < -0.07
        cv2.line(vis, ear_mid, sh_mid, SLOUCH_C if elev_bad else UPRIGHT_C, 3)

        for pt in [l_ear, r_ear, l_sh, r_sh]:
            cv2.circle(vis, pt, 8, main_color, -1)
            cv2.circle(vis, pt, 8, (255, 255, 255), 2)

    h, w = vis.shape[:2]
    cv2.rectangle(vis, (0, 0), (w - 1, h - 1), main_color, 6)

    panel = np.zeros((70, w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 30)

    label_str = "SLOUCHED" if label == "slouched" else "upright" if label == "upright" else "unknown"
    cv2.putText(panel, label_str, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, main_color, 2)

    if dev:
        info = f"elev:{dev.get('shoulder_elevation', 0):+.3f}  tilt:{dev.get('shoulder_tilt', 0):+.3f}  conf:{result['confidence']:.2f}"
    else:
        info = f"elev:{m.get('shoulder_elevation', 0):.3f}  tilt:{m.get('shoulder_tilt', 0):.3f}  conf:{result['confidence']:.2f}"
    cv2.putText(panel, info, (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    return np.vstack([vis, panel])


if __name__ == "__main__":
    import sys
    import cv2
    import json

    VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\lenac\Pictures\Camera Roll\WIN_20260524_22_57_28_Pro.mp4"

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("영상을 열 수 없습니다:", VIDEO_PATH)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = int(total_frames / fps)
    analyzer = PostureAnalyzer()

    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - int(fps * 5)))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        analyzer.feed_calibration(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    ok_calib = analyzer.finalize_calibration()
    print(f"캘리브레이션 {'완료' if ok_calib else '실패 → 절대 임계값 모드'}")

    frames_out = []
    frame_records = []

    for sec in range(duration + 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * fps))
        ok, frame = cap.read()
        if not ok:
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = analyzer.analyze(frame_rgb)

        frame_records.append({
            "sec": sec,
            "label": res["label"],
            "confidence": res["confidence"],
        })

        lm_pts = {}
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        det = analyzer._landmarker.detect(mp_img)
        if det.pose_landmarks:
            lm = det.pose_landmarks[0]
            h, w = frame.shape[:2]
            def to_px(idx):
                return (int(lm[idx].x * w), int(lm[idx].y * h))
            lm_pts = {
                "l_ear": to_px(LEFT_EAR), "r_ear": to_px(RIGHT_EAR),
                "l_sh": to_px(LEFT_SHOULDER), "r_sh": to_px(RIGHT_SHOULDER),
            }

        overlay = _draw_overlay(frame, res, lm_pts)
        cv2.putText(overlay, f"{sec}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
        frames_out.append(overlay)

    cap.release()
    analyzer.close()

    # JSON 결과 저장
    slouched = sum(1 for r in frame_records if r["label"] == "slouched")
    upright = sum(1 for r in frame_records if r["label"] == "upright")
    unknown = sum(1 for r in frame_records if r["label"] == "unknown")
    total = len(frame_records)

    output = {
        "slouched": slouched,
        "upright": upright,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posture_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 분석 결과 ===")
    print(f"총 {total}프레임 | 구부정: {slouched}회 | 정자세: {upright}회 | 미감지: {unknown}회")
    print(f"결과 저장됨: {out_path}")

    # 시각화
    COLS = 5
    TW, TH = 320, 310

    rows = (len(frames_out) + COLS - 1) // COLS
    grid = np.zeros((rows * TH, COLS * TW, 3), dtype=np.uint8)

    for i, f in enumerate(frames_out):
        r, c = divmod(i, COLS)
        grid[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = cv2.resize(f, (TW, TH))

    cv2.namedWindow("Posture Analysis", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Posture Analysis", min(COLS * TW, 1600), min(rows * TH, 1000))
    cv2.imshow("Posture Analysis", grid)
    print("아무 키나 누르면 종료.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
