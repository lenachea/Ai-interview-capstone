import mediapipe as mp
import cv2
import numpy as np
from collections import deque, Counter

MODEL_PATH  = "/workspace/CSM/nonverbal_module/pose_landmarker.task"
VIDEO_PATH  = "/workspace/CSM/WIN_20260518_14_18_03_Pro (1).mp4"
OUTPUT_DIR  = "/workspace/CSM/nonverbal_module/posture_frames"

import os
os.makedirs(OUTPUT_DIR, exist_ok=True)

BaseOptions       = mp.tasks.BaseOptions
PoseLandmarker    = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = PoseLandmarkerOptions(
    base_options=BaseOptions(
        model_asset_path=MODEL_PATH,
        delegate=BaseOptions.Delegate.CPU
    ),
    running_mode=VisionRunningMode.VIDEO
)

NOSE           = 0
LEFT_SHOULDER  = 11
RIGHT_SHOULDER = 12
LEFT_HIP       = 23
RIGHT_HIP      = 24
MAX_SCORE      = 100

POSE_CONNECTIONS = [
    (11,12),(11,13),(13,15),(12,14),(14,16),
    (11,23),(12,24),(23,24)
]


class PostureAnalyzer:
    """2D 어깨 수평과 MediaPipe 3D world landmarks를 함께 사용한다."""

    def __init__(self, calibration_frames=60, smooth_len=30):
        self.calibration_frames = calibration_frames
        self.samples = []
        self.baseline = None
        self.score_window = deque(maxlen=smooth_len)
        self.score_history = []
        self.component_scores = {}
        self.issue_counts = Counter()

    @property
    def is_calibrating(self):
        return self.baseline is None

    @staticmethod
    def _point2(landmarks, idx):
        lm = landmarks[idx]
        return np.array([lm.x, lm.y], dtype=np.float32)

    @staticmethod
    def _point3(landmarks, idx):
        lm = landmarks[idx]
        return np.array([lm.x, lm.y, lm.z], dtype=np.float32)

    def _extract_features(self, landmarks_2d, landmarks_3d):
        # 상반신 영상에서는 골반이 화면 밖이어도 코와 어깨가 선명하면 분석한다.
        required = [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]
        if any(getattr(landmarks_2d[idx], "visibility", 1.0) < 0.35 for idx in required):
            return None
        hip_visibility = min(
            getattr(landmarks_2d[LEFT_HIP], "visibility", 0.0),
            getattr(landmarks_2d[RIGHT_HIP], "visibility", 0.0),
        )

        l_sho_2d = self._point2(landmarks_2d, LEFT_SHOULDER)
        r_sho_2d = self._point2(landmarks_2d, RIGHT_SHOULDER)
        shoulder_delta_2d = r_sho_2d - l_sho_2d
        shoulder_roll = float(np.degrees(np.arctan2(
            abs(shoulder_delta_2d[1]), max(abs(shoulder_delta_2d[0]), 1e-6)
        )))

        nose = self._point3(landmarks_3d, NOSE)
        l_sho = self._point3(landmarks_3d, LEFT_SHOULDER)
        r_sho = self._point3(landmarks_3d, RIGHT_SHOULDER)
        l_hip = self._point3(landmarks_3d, LEFT_HIP)
        r_hip = self._point3(landmarks_3d, RIGHT_HIP)

        shoulder_center = (l_sho + r_sho) / 2
        hip_center = (l_hip + r_hip) / 2
        shoulder_width = max(float(np.linalg.norm(l_sho - r_sho)), 1e-6)
        torso = shoulder_center - hip_center

        # 수직축(y)에 대한 몸통의 3차원 기울기
        torso_lean_3d = float(np.degrees(np.arctan2(
            np.linalg.norm(torso[[0, 2]]), max(abs(float(torso[1])), 1e-6)
        )))
        # 어깨 중심 대비 머리의 앞뒤(z) 위치와 높이(y)를 체격으로 정규화
        head_forward_3d = float(nose[2] - shoulder_center[2]) / shoulder_width
        head_height_3d = float(shoulder_center[1] - nose[1]) / shoulder_width
        # 한쪽 어깨가 카메라 쪽으로 돌아간 정도
        shoulder_depth = abs(float(l_sho[2] - r_sho[2])) / shoulder_width

        return {
            "shoulder_roll": shoulder_roll,
            "torso_lean_3d": torso_lean_3d,
            "head_forward_3d": head_forward_3d,
            "head_height_3d": head_height_3d,
            "shoulder_depth": shoulder_depth,
            "hip_visibility": float(hip_visibility),
        }

    @staticmethod
    def _score(deviation, allowed, bad):
        ratio = (deviation - allowed) / max(bad - allowed, 1e-6)
        return float(np.clip(100 * (1 - ratio), 0, 100))

    def update(self, landmarks_2d, landmarks_3d):
        features = self._extract_features(landmarks_2d, landmarks_3d)
        if features is None:
            return []

        if self.baseline is None:
            self.samples.append(features)
            if len(self.samples) >= self.calibration_frames:
                self.baseline = {
                    key: float(np.median([sample[key] for sample in self.samples]))
                    for key in features
                }
            # 보정 중의 임의 100점은 이동평균에 넣지 않는다.
            return []

        deviations = {
            "shoulder": abs(features["shoulder_roll"] - self.baseline["shoulder_roll"]),
            "torso": abs(features["torso_lean_3d"] - self.baseline["torso_lean_3d"]),
            "head_forward": abs(features["head_forward_3d"] - self.baseline["head_forward_3d"]),
            "head_drop": max(0.0, self.baseline["head_height_3d"] - features["head_height_3d"]),
            "rotation": abs(features["shoulder_depth"] - self.baseline["shoulder_depth"]),
        }
        components = {
            "shoulder": self._score(deviations["shoulder"], 2.0, 12.0),
            "torso": (
                self._score(deviations["torso"], 3.0, 18.0)
                if features["hip_visibility"] >= 0.20
                and self.baseline["hip_visibility"] >= 0.20
                else None
            ),
            "head_forward": self._score(deviations["head_forward"], 0.05, 0.30),
            "head_drop": self._score(deviations["head_drop"], 0.04, 0.25),
            "rotation": self._score(deviations["rotation"], 0.05, 0.30),
        }
        weights = {
            "shoulder": 0.20,
            "torso": 0.25,
            "head_forward": 0.25,
            "head_drop": 0.20,
            "rotation": 0.10,
        }
        active_weight = sum(weights[key] for key, value in components.items() if value is not None)
        raw_score = sum(
            value * weights[key] for key, value in components.items() if value is not None
        ) / active_weight
        self.score_window.append(raw_score)
        smoothed_score = float(np.mean(self.score_window))
        self.score_history.append(smoothed_score)
        self.component_scores = components

        labels = {
            "shoulder": "어깨 수평 불균형",
            "torso": "3D 상체 기울어짐",
            "head_forward": "머리가 앞으로 나옴",
            "head_drop": "머리 숙임/구부정함",
            "rotation": "상체가 한쪽으로 돌아감",
        }
        messages = []
        for key, value in components.items():
            if value is not None and value < 65:
                messages.append(labels[key])
                self.issue_counts[key] += 1
        return messages

    def current_score(self):
        if not self.score_window:
            return 100.0
        return float(np.mean(self.score_window))

    def final_score(self):
        if not self.score_history:
            return self.current_score()
        return float(np.mean(self.score_history))


def draw_pose(frame, landmarks, h, w, has_violation):
    color = (0, 0, 220) if has_violation else (0, 220, 0)
    for i, j in POSE_CONNECTIONS:
        if i < len(landmarks) and j < len(landmarks):
            x1, y1 = int(landmarks[i].x * w), int(landmarks[i].y * h)
            x2, y2 = int(landmarks[j].x * w), int(landmarks[j].y * h)
            cv2.line(frame, (x1, y1), (x2, y2), color, 2)
    for idx in [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER, 13, 14, 15, 16, 23, 24]:
        if idx < len(landmarks):
            cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
            cv2.circle(frame, (cx, cy), 6, color, -1)


def run():
    cap   = cv2.VideoCapture(VIDEO_PATH)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30
    W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 10개 프레임만 균등 간격으로 저장
    save_at = set(int(total * i / 10) for i in range(10))

    analyzer  = PostureAnalyzer(calibration_frames=max(15, int(fps * 2)), smooth_len=max(5, int(fps)))
    saved     = 0

    with PoseLandmarker.create_from_options(options) as landmarker:
        frame_num = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(frame_num * 1000 / fps)
            result   = landmarker.detect_for_video(mp_image, timestamp_ms)

            frame_violations = []
            if result.pose_landmarks and result.pose_world_landmarks:
                frame_violations = analyzer.update(
                    result.pose_landmarks[0], result.pose_world_landmarks[0]
                )
                draw_pose(frame, result.pose_landmarks[0], H, W, bool(frame_violations))

            score = analyzer.current_score()

            # 상단 점수
            bar_color = (0, 200, 0) if score >= 70 else (0, 165, 255) if score >= 40 else (0, 0, 220)
            cv2.rectangle(frame, (0, 0), (W, 145), (20, 20, 20), -1)
            score_label = "Calibrating..." if analyzer.is_calibrating else f"Posture Score: {score:.1f}/100"
            cv2.putText(frame, score_label,
                        (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.2, bar_color, 4)
            if analyzer.component_scores:
                c = analyzer.component_scores
                detail = (
                    f"Shoulder {c['shoulder']:.0f}  "
                    f"Torso3D {c['torso']:.0f}  " if c['torso'] is not None else
                    f"Shoulder {c['shoulder']:.0f}  Torso3D N/A  "
                ) + (
                    f"Forward3D {c['head_forward']:.0f}  Drop3D {c['head_drop']:.0f}  "
                    f"Rotation3D {c['rotation']:.0f}"
                )
                cv2.putText(frame, detail, (10, 125),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 220, 220), 2)

            # 위반 메시지
            for i, msg in enumerate(frame_violations):
                cv2.putText(frame, f"! {msg}", (10, H - 15 - i * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)

            if frame_num in save_at:
                path = os.path.join(OUTPUT_DIR, f"frame_{frame_num:05d}.jpg")
                cv2.imwrite(path, frame)
                saved += 1
                print(f"  저장: {path}")

            frame_num += 1

    cap.release()

    score = analyzer.final_score()
    print(f"\n{'='*40}")
    print(f"최종 평균 점수:   {score:.1f} / 100")
    print(f"어깨 불균형 프레임: {analyzer.issue_counts.get('shoulder', 0)}개")
    print(f"3D 상체 기울임:     {analyzer.issue_counts.get('torso', 0)}개")
    print(f"머리 전방 이동:     {analyzer.issue_counts.get('head_forward', 0)}개")
    print(f"머리 숙임 프레임:   {analyzer.issue_counts.get('head_drop', 0)}개")
    print(f"상체 회전 프레임:   {analyzer.issue_counts.get('rotation', 0)}개")
    print(f"시각화 프레임 저장: {OUTPUT_DIR}  ({saved}장)")

if __name__ == "__main__":
    run()
