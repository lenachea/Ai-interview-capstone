import os
import sys

# ONNX Runtime CUDA 11.8 전용 라이브러리를 이 파일에서만 사용한다.
if os.environ.get("RTMPOSE_CUDA_READY") != "1":
    lib_dirs = [
        "/workspace/.rtmpose_cuda/nvidia/cudnn/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cuda_nvrtc/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/nccl/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cublas/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cuda_runtime/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cuda_cupti/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cufft/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cusolver/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/nvtx/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/cusparse/lib",
        "/opt/conda/envs/csm/lib/python3.11/site-packages/nvidia/curand/lib",
    ]
    os.environ["LD_LIBRARY_PATH"] = ":".join(lib_dirs + [os.environ.get("LD_LIBRARY_PATH", "")])
    os.environ["RTMPOSE_CUDA_READY"] = "1"
    os.execv(sys.executable, [sys.executable, *sys.argv])

import argparse
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from rtmlib import Wholebody3d

DEFAULT_VIDEO = ""  # 실행 시 인자로 영상 경로 전달
DEFAULT_OUTPUT = str(Path(__file__).resolve().parent / "posture_rtmpose_frames")

NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_HIP = 11
RIGHT_HIP = 12
CONNECTIONS = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12)]


class PostureAnalyzer3D:
    def __init__(self, calibration_frames, smooth_frames):
        self.calibration_frames = calibration_frames
        self.samples = []
        self.baseline = None
        self.window = deque(maxlen=smooth_frames)
        self.history = []
        self.components = {}
        self.issue_counts = Counter()

    @property
    def calibrating(self):
        return self.baseline is None

    @staticmethod
    def score(deviation, allowed, bad):
        ratio = (deviation - allowed) / max(bad - allowed, 1e-6)
        return float(np.clip(100.0 * (1.0 - ratio), 0.0, 100.0))

    def features(self, keypoints_3d, keypoints_2d, scores):
        upper = [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]
        if min(float(scores[i]) for i in upper) < 0.35:
            return None

        ls2, rs2 = keypoints_2d[LEFT_SHOULDER], keypoints_2d[RIGHT_SHOULDER]
        delta = rs2 - ls2
        shoulder_angle_signed = float(np.degrees(np.arctan2(
            delta[1], max(abs(delta[0]), 1e-6)
        )))
        shoulder_roll = abs(shoulder_angle_signed)

        # 눈 선을 우선 사용하고, 눈 신뢰도가 낮으면 귀 선을 사용한다.
        if min(float(scores[LEFT_EYE]), float(scores[RIGHT_EYE])) >= 0.30:
            head_left, head_right = keypoints_2d[LEFT_EYE], keypoints_2d[RIGHT_EYE]
            head_tilt_confidence = min(float(scores[LEFT_EYE]), float(scores[RIGHT_EYE]))
        elif min(float(scores[LEFT_EAR]), float(scores[RIGHT_EAR])) >= 0.30:
            head_left, head_right = keypoints_2d[LEFT_EAR], keypoints_2d[RIGHT_EAR]
            head_tilt_confidence = min(float(scores[LEFT_EAR]), float(scores[RIGHT_EAR]))
        else:
            head_left = head_right = None
            head_tilt_confidence = 0.0

        head_tilt = 0.0
        if head_left is not None:
            head_delta = head_right - head_left
            head_angle = float(np.degrees(np.arctan2(
                head_delta[1], max(abs(head_delta[0]), 1e-6)
            )))
            # 어깨선 기준 상대 각도라 카메라 자체 기울기의 영향을 줄인다.
            head_tilt = head_angle - shoulder_angle_signed

        nose = keypoints_3d[NOSE].astype(np.float64)
        ls = keypoints_3d[LEFT_SHOULDER].astype(np.float64)
        rs = keypoints_3d[RIGHT_SHOULDER].astype(np.float64)
        shoulder_center = (ls + rs) / 2.0
        shoulder_width = max(float(np.linalg.norm(ls - rs)), 1e-6)

        head_forward = float(nose[2] - shoulder_center[2]) / shoulder_width
        head_height = float(shoulder_center[1] - nose[1]) / shoulder_width
        shoulder_depth = abs(float(ls[2] - rs[2])) / shoulder_width

        hip_confidence = min(float(scores[LEFT_HIP]), float(scores[RIGHT_HIP]))
        torso_lean = 0.0
        if hip_confidence >= 0.30:
            hip_center = (keypoints_3d[LEFT_HIP] + keypoints_3d[RIGHT_HIP]) / 2.0
            torso = shoulder_center - hip_center
            torso_lean = float(np.degrees(np.arctan2(
                np.linalg.norm(torso[[0, 2]]), max(abs(float(torso[1])), 1e-6)
            )))

        return {
            "shoulder_roll": shoulder_roll,
            "head_tilt": head_tilt,
            "head_tilt_confidence": head_tilt_confidence,
            "head_forward": head_forward,
            "head_height": head_height,
            "shoulder_depth": shoulder_depth,
            "torso_lean": torso_lean,
            "hip_confidence": hip_confidence,
        }

    def update(self, keypoints_3d, keypoints_2d, scores):
        f = self.features(keypoints_3d, keypoints_2d, scores)
        if f is None:
            return []
        if self.baseline is None:
            self.samples.append(f)
            if len(self.samples) >= self.calibration_frames:
                self.baseline = {
                    key: float(np.median([sample[key] for sample in self.samples])) for key in f
                }
            return []

        torso_available = f["hip_confidence"] >= 0.30 and self.baseline["hip_confidence"] >= 0.30
        tilt_available = (
            f["head_tilt_confidence"] >= 0.30
            and self.baseline["head_tilt_confidence"] >= 0.30
        )
        components = {
            "shoulder": self.score(abs(f["shoulder_roll"] - self.baseline["shoulder_roll"]), 2.0, 12.0),
            "torso": self.score(abs(f["torso_lean"] - self.baseline["torso_lean"]), 3.0, 18.0) if torso_available else None,
            # 어깨선 대비 고개의 실제 좌우 기울기를 평가한다.
            # 초반 기준 자세가 이미 삐딱한 경우에도 이를 정상으로 보정하지 않는다.
            "head_tilt": self.score(abs(f["head_tilt"]), 3.0, 15.0) if tilt_available else None,
            "forward": self.score(abs(f["head_forward"] - self.baseline["head_forward"]), 0.04, 0.25),
            # 머리 높이가 기준보다 낮아지는 구부정 자세를 강하게 반영한다.
            "drop": self.score(max(0.0, self.baseline["head_height"] - f["head_height"]), 0.015, 0.12),
            "rotation": self.score(abs(f["shoulder_depth"] - self.baseline["shoulder_depth"]), 0.04, 0.25),
        }
        weights = {
            "shoulder": 0.10,
            "torso": 0.10,
            "head_tilt": 0.15,
            "forward": 0.20,
            "drop": 0.35,
            "rotation": 0.10,
        }
        active = sum(weights[k] for k, v in components.items() if v is not None)
        raw = sum(weights[k] * v for k, v in components.items() if v is not None) / active
        self.window.append(raw)
        current = float(np.mean(self.window))
        self.history.append(current)
        self.components = components

        labels = {
            "shoulder": "shoulder imbalance",
            "torso": "3D torso lean",
            "head_tilt": "head tilted sideways",
            "forward": "forward head",
            "drop": "head drop/slouch",
            "rotation": "torso rotation",
        }
        issues = []
        for key, value in components.items():
            if value is not None and value < 65:
                issues.append(labels[key])
                self.issue_counts[key] += 1
        return issues

    def current_score(self):
        return float(np.mean(self.window)) if self.window else 100.0

    def final_score(self):
        return float(np.mean(self.history)) if self.history else self.current_score()


def select_main_person(keypoints_2d, scores):
    if len(keypoints_2d) == 0:
        return None
    ranking = []
    for i in range(len(keypoints_2d)):
        shoulder_width = float(np.linalg.norm(
            keypoints_2d[i, LEFT_SHOULDER] - keypoints_2d[i, RIGHT_SHOULDER]
        ))
        confidence = float(np.mean(scores[i, [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]]))
        ranking.append(shoulder_width * max(confidence, 0.0))
    return int(np.argmax(ranking))


def draw_pose(frame, points, scores, bad):
    color = (0, 0, 220) if bad else (0, 220, 0)
    for a, b in CONNECTIONS:
        if scores[a] >= 0.3 and scores[b] >= 0.3:
            cv2.line(frame, tuple(points[a].astype(int)), tuple(points[b].astype(int)), color, 3)
    for idx in {i for pair in CONNECTIONS for i in pair} | {NOSE, LEFT_EYE, RIGHT_EYE}:
        if scores[idx] >= 0.3:
            cv2.circle(frame, tuple(points[idx].astype(int)), 6, color, -1)


def run(video_path, output_dir, sample_fps):
    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(f"CUDAExecutionProvider를 사용할 수 없습니다: {providers}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"동영상을 열 수 없습니다: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_stride = max(1, int(round(fps / max(sample_fps, 1.0))))
    analysis_fps = fps / frame_stride
    save_at = {
        min(total - 1, int(round((total * i / 10) / frame_stride)) * frame_stride)
        for i in range(10)
    }
    # 처리된 프레임 기준 2초 보정, 약 0.4초 이동평균
    analyzer = PostureAnalyzer3D(
        max(10, int(analysis_fps * 2)), max(3, int(analysis_fps * 0.4))
    )
    print(
        f"video fps: {fps:.2f}, analysis fps: {analysis_fps:.2f} "
        f"(every {frame_stride} frame)"
    )

    model = Wholebody3d(backend="onnxruntime", device="cuda")
    actual = [model.det_model.session.get_providers(), model.pose_model.session.get_providers()]
    if any("CUDAExecutionProvider" not in p for p in actual):
        raise RuntimeError(f"모델이 GPU로 초기화되지 않았습니다: {actual}")
    print(f"GPU providers: {actual}")

    frame_idx = saved = detected = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        keypoints_3d, scores, _, keypoints_2d = model(frame)
        person = select_main_person(keypoints_2d, scores)
        issues = []
        if person is not None:
            detected += 1
            issues = analyzer.update(keypoints_3d[person], keypoints_2d[person], scores[person])
            draw_pose(frame, keypoints_2d[person], scores[person], bool(issues))

        score = analyzer.current_score()
        color = (0, 200, 0) if score >= 70 else (0, 165, 255) if score >= 40 else (0, 0, 220)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 145), (20, 20, 20), -1)
        title = "Calibrating RTMW3D..." if analyzer.calibrating else f"RTMW3D Posture: {score:.1f}/100"
        cv2.putText(frame, title, (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.8, color, 4)
        if analyzer.components:
            c = analyzer.components
            torso = "N/A" if c["torso"] is None else f"{c['torso']:.0f}"
            tilt = "N/A" if c["head_tilt"] is None else f"{c['head_tilt']:.0f}"
            detail = (
                f"Shoulder {c['shoulder']:.0f}  Torso {torso}  Tilt {tilt}  "
                f"Forward {c['forward']:.0f}  Drop {c['drop']:.0f}  Rotation {c['rotation']:.0f}"
            )
            cv2.putText(frame, detail, (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (220, 220, 220), 2)
        for i, issue in enumerate(issues):
            cv2.putText(frame, f"! {issue}", (10, frame.shape[0] - 15 - i * 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)

        if frame_idx in save_at:
            path = output / f"frame_{frame_idx:05d}.jpg"
            cv2.imwrite(str(path), frame)
            saved += 1
            print(f"saved: {path}")
        frame_idx += 1

    cap.release()
    print("\n" + "=" * 48)
    print(f"final average score: {analyzer.final_score():.1f} / 100")
    analyzed = (frame_idx + frame_stride - 1) // frame_stride
    print(f"detected/analyzed frames: {detected} / {analyzed}")
    print(f"skipped source frames: {max(0, frame_idx - analyzed)}")
    print(f"shoulder imbalance: {analyzer.issue_counts['shoulder']}")
    print(f"3D torso lean: {analyzer.issue_counts['torso']}")
    print(f"sideways head tilt: {analyzer.issue_counts['head_tilt']}")
    print(f"forward head: {analyzer.issue_counts['forward']}")
    print(f"head drop/slouch: {analyzer.issue_counts['drop']}")
    print(f"torso rotation: {analyzer.issue_counts['rotation']}")
    print(f"output: {output} ({saved} images)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTMW3D CUDA upper-body posture analyzer")
    parser.add_argument("video", nargs="?", default=DEFAULT_VIDEO)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--sample-fps", type=float, default=1,
        help="초당 분석 프레임 수 (기본 10, 빠른 실행은 5)",
    )
    args = parser.parse_args()
    run(args.video, args.output, args.sample_fps)
