"""
vision_features.py
-------------------
영상 파일 하나를 직접 샘플링해 시선·표정·자세 raw feature를 뽑는 단일 소스.

eval_model/scripts/extract_features.py 가 36개 학습 영상에서 뽑았던 것과
"완전히 동일한" 코드로 라이브 백엔드 분석에서도 같은 feature를 뽑기 위해
분리했다 — 학습 때 쓴 알고리즘과 실서비스가 쓰는 알고리즘이 다르면
(예: 이전 nonverbal_module/api.py는 자세를 upperbody_movement.PostureAnalyzer로,
학습은 posture_rtmpose_3d.PostureAnalyzer3D로 뽑아 서로 다른 지표였음)
학습된 모델이 실제 입력 분포에서 무의미해진다.

반환 feature 이름은 eval_model/data/features/*.json 과 동일한 스키마를 따른다
(gaze_*, emo_*, posture_* — 총 35개, 언어 feature 17개는 verbal_module 쪽에서 따로 합류).
"""
from __future__ import annotations

import glob
import math
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

# hsemotion 실제 출력 라벨(긴 이름) — 예전 emotion_classifier.py는 "Happy"/"Sad"로 잘못
# 가정해서 해당 프레임들이 전부 누락되는 버그가 있었다. 여기서는 실측 라벨을 그대로 쓴다.
EMOTION_NEGATIVE = {"Anger", "Contempt", "Disgust", "Fear", "Sadness"}
EMOTION_POSITIVE = {"Happiness", "Neutral", "Surprise"}
EMOTION_LABELS = ["Anger", "Contempt", "Disgust", "Fear", "Happiness", "Neutral", "Sadness", "Surprise"]

DEFAULT_SAMPLE_FPS = 2.0


def _set_rtmpose_cuda_ready():
    """posture_rtmpose_3d.py는 import 시 RTMPOSE_CUDA_READY가 없으면 LD_LIBRARY_PATH를
    재설정하고 os.execv로 프로세스 전체를 재실행한다 — FastAPI 서버 프로세스 안에서
    이게 발생하면 서버 자체가 재시작되어버리므로, import 전에 반드시 미리 세팅해
    이 분기를 건너뛰게 한다. (LD_LIBRARY_PATH는 이미 올바르게 설정되어 있어야 함)
    """
    os.environ.setdefault("RTMPOSE_CUDA_READY", "1")


def _load_posture_module():
    _set_rtmpose_cuda_ready()
    import importlib.util
    path = _DIR / "posture_rtmpose_3d.py"
    spec = importlib.util.spec_from_file_location("posture_rtmpose_3d", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summarize_negative_emotion(emotion_log: list[dict]) -> list[dict]:
    """연속된 부정적 표정 프레임을 하나의 구간으로 묶는다 (eye_tracker.summarize_gaze의
    deviated_segments와 동일한 방식) — 사용자가 "이 순간에 무슨 생각을 했는지" 다시
    확인할 수 있도록 타임스탬프 구간을 제공한다."""
    segments = []
    seg_start = None
    seg_labels: list[str] = []

    for i, e in enumerate(emotion_log):
        is_neg = e["emotion"] in EMOTION_NEGATIVE
        if is_neg and seg_start is None:
            seg_start = e["time"]
            seg_labels = [e["emotion"]]
        elif is_neg:
            seg_labels.append(e["emotion"])
        elif seg_start is not None:
            segments.append({
                "start": seg_start,
                "end": emotion_log[i - 1]["time"],
                "emotion": Counter(seg_labels).most_common(1)[0][0],
            })
            seg_start = None

    if seg_start is not None:
        segments.append({
            "start": seg_start,
            "end": emotion_log[-1]["time"],
            "emotion": Counter(seg_labels).most_common(1)[0][0],
        })

    return segments


# ── 시선 + 표정 (프레임 1회 순회로 함께 처리) ────────────────────────────────

def extract_gaze_emotion(video_path: str, sample_fps: float = DEFAULT_SAMPLE_FPS,
                          device: str = "cuda") -> dict:
    """
    표정은 hsemotion, 시선은 L2CS-Net(ResNet50 기반 yaw/pitch 회귀, Gaze360 사전학습)으로 뽑는다.

    시선을 MediaPipe blendshape 대신 L2CS-Net으로 바꾼 이유: blendshape 방식은
    안경 착용 등 개인차로 정면을 봐도 특정 방향 수치가 구조적으로 높게 나와
    계속 같은 방향으로 오분류되는 문제가 실측 확인됨. L2CS-Net도 얼굴 crop 방식/
    카메라 위치에 따라 개인별 상수 오프셋(예: yaw +13~16도)이 남아서, 영상 전체의
    중앙값을 baseline으로 잡고 거기서 벗어난 정도로 최종 방향을 판정한다
    (posture_rtmpose_3d.PostureAnalyzer3D가 이미 쓰는 것과 같은 보정 방식).
    """
    from eye_tracker import _create_detector, detect_cropped_face, gaze_signals, summarize_gaze
    from hsemotion.facial_emotions import HSEmotionRecognizer
    from l2cs_gaze import predict_gaze, classify_direction

    detector = _create_detector()
    try:
        fer = HSEmotionRecognizer(model_name="enet_b2_8", device=device)
    except Exception:
        fer = HSEmotionRecognizer(model_name="enet_b2_8", device="cpu")

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(fps / max(sample_fps, 0.1))))

    gaze_samples = []  # [(time, yaw, pitch)] — blink 프레임 제외, calibration 후 분류
    blink_log = {}     # time -> True (blink 프레임은 여기서 바로 "blink"로 확정)
    emotions, emo_confs, emotion_log = [], [], []
    frame_idx = sampled = face_found = 0

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride:
            frame_idx += 1
            continue

        sampled += 1
        cropped, result = detect_cropped_face(frame, detector)

        if result.face_landmarks and result.face_blendshapes:
            face_found += 1
            t = round(frame_idx / fps, 2)
            rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)

            if gaze_signals(result.face_blendshapes[0])["blink"] > 0.5:
                blink_log[t] = True
            else:
                try:
                    yaw, pitch = predict_gaze(rgb, device=device)
                    gaze_samples.append((t, yaw, pitch))
                except Exception:
                    pass

            try:
                label, scores = fer.predict_emotions(rgb, logits=False)
                emotions.append(label)
                emo_confs.append(float(np.max(scores)))
                emotion_log.append({"time": t, "emotion": label})
            except Exception:
                pass

        frame_idx += 1

    cap.release()

    # ── L2CS 절대각도(카메라 기준)를 그대로 판정에 사용 ──────────────────────
    # 영상별 중앙값을 baseline으로 빼는 방식은 "이 사람이 평소 카메라 대비
    # 비스듬히 보는 게 정상 상태"인 경우, 오히려 진짜 정면(raw yaw≈0)을
    # "이탈"로 뒤집어버리는 문제가 실측 확인됨(t=3초: raw yaw=-2°인데
    # baseline(15.8°) 대비로는 이탈 판정됨). L2CS는 yaw/pitch=0이 "카메라
    # 정면 응시"로 학습된 물리적 기준이 있으므로, 넉넉한 절대 threshold로
    # 직접 판정하는 편이 더 안정적이다.
    gaze_log = [{"time": t, "direction": "blink"} for t in blink_log]
    for t, yaw, pitch in gaze_samples:
        direction = classify_direction(yaw, pitch)
        gaze_log.append({"time": t, "direction": direction})
    gaze_log.sort(key=lambda g: g["time"])

    gaze = summarize_gaze(gaze_log)
    ratios = gaze.get("direction_ratios", {})
    segs = gaze.get("deviated_segments", []) or []
    seg_durs = [float(s["end"]) - float(s["start"]) for s in segs]

    counts = Counter(emotions)
    n_emo = max(len(emotions), 1)
    probs = [c / n_emo for c in counts.values()]
    entropy = -sum(p * math.log(p + 1e-12) for p in probs)
    changes = sum(1 for a, b in zip(emotions, emotions[1:]) if a != b)
    expression_deductions = _summarize_negative_emotion(emotion_log)

    return {
        "gaze_center_ratio": float(gaze.get("gaze_ratio") or 0.0),
        "gaze_left_ratio": float(ratios.get("left") or 0.0),
        "gaze_right_ratio": float(ratios.get("right") or 0.0),
        "gaze_up_ratio": float(ratios.get("up") or 0.0),
        "gaze_down_ratio": float(ratios.get("down") or 0.0),
        "gaze_blink_ratio": float(ratios.get("blink") or 0.0),
        "gaze_deviation_count": len(segs),
        "gaze_deviation_mean_sec": float(np.mean(seg_durs)) if seg_durs else 0.0,
        "gaze_deviation_max_sec": float(max(seg_durs)) if seg_durs else 0.0,
        "face_detect_ratio": face_found / max(sampled, 1),
        "emo_neutral_ratio": counts.get("Neutral", 0) / n_emo,
        "emo_happy_ratio": counts.get("Happiness", 0) / n_emo,
        "emo_negative_ratio": sum(counts.get(e, 0) for e in EMOTION_NEGATIVE) / n_emo,
        "emo_surprise_ratio": counts.get("Surprise", 0) / n_emo,
        "emo_entropy": float(entropy),
        "emo_unique_count": len(counts),
        "emo_change_rate": changes / max(len(emotions) - 1, 1),
        "emo_mean_confidence": float(np.mean(emo_confs)) if emo_confs else 0.0,
        "frames_sampled": sampled,
        "_expression_deductions": expression_deductions,
        # 프론트엔드/기존 nonverbal_analysis 표시용 요약(하위호환)
        "_gaze_summary": gaze,
        "_emotion_counts": dict(counts),
    }


# ── 자세 (RTMW3D, posture_rtmpose_3d.PostureAnalyzer3D) ─────────────────────

def extract_posture(video_path: str, sample_fps: float = DEFAULT_SAMPLE_FPS,
                     device: str = "cuda") -> dict:
    posture_mod = _load_posture_module()
    from rtmlib import Wholebody3d

    try:
        pose_model = Wholebody3d(backend="onnxruntime", device=device)
    except Exception:
        pose_model = Wholebody3d(backend="onnxruntime", device="cpu")

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(fps / max(sample_fps, 0.1))))
    analysis_fps = fps / stride

    analyzer = posture_mod.PostureAnalyzer3D(
        max(10, int(analysis_fps * 2)), max(3, int(analysis_fps * 0.4))
    )
    component_log = {k: [] for k in ("shoulder", "torso", "head_tilt", "forward", "drop", "rotation")}
    deductions = []
    frame_idx = analyzed = detected = 0

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride:
            frame_idx += 1
            continue

        analyzed += 1
        sec = round(frame_idx / fps, 1)
        keypoints_3d, scores, _, keypoints_2d = pose_model(frame)
        person = posture_mod.select_main_person(keypoints_2d, scores)
        if person is not None:
            detected += 1
            analyzer.update(keypoints_3d[person], keypoints_2d[person], scores[person])
            for key, value in (analyzer.components or {}).items():
                if value is not None:
                    component_log[key].append(value)
            current = analyzer.history[-1] if analyzer.history else None
            if current is not None and current < 65:
                deductions.append({"sec": sec, "confidence": round((100.0 - current) / 100.0, 3)})

        frame_idx += 1

    cap.release()

    history = analyzer.history or []
    issue_total = max(len(history), 1)
    out = {
        "posture_score_mean": float(np.mean(history)) if history else float("nan"),
        "posture_score_std": float(np.std(history)) if history else float("nan"),
        "posture_score_min": float(np.min(history)) if history else float("nan"),
        "posture_score_p25": float(np.percentile(history, 25)) if history else float("nan"),
        "pose_detect_ratio": detected / max(analyzed, 1),
        "_posture_deductions": deductions,
        "_history_len": len(history),
    }
    for key, values in component_log.items():
        out[f"posture_{key}_mean"] = float(np.mean(values)) if values else float("nan")
        out[f"posture_{key}_issue_rate"] = analyzer.issue_counts.get(key, 0) / issue_total
    return out


# ── 통합 + 기존 coarse score(0~100) 하위호환 ─────────────────────────────────

def _bucket(value: float, thresholds: list[tuple[float, int]], default: int = 40) -> int:
    """thresholds: [(min_value, score), ...] 내림차순으로 정렬돼 있다고 가정."""
    for min_v, score in thresholds:
        if value >= min_v:
            return score
    return default


def analyze_video(video_path: str, sample_fps: float = DEFAULT_SAMPLE_FPS) -> dict:
    """
    영상 파일 하나를 받아 시선·표정·자세를 모두 분석한다.

    Returns
    -------
    {
        "raw_features": {...}       # eval_model dataset.csv와 동일 스키마 (gaze_*, emo_*, posture_*)
        "eye_contact_score":       int | None,   # 기존 nonverbal_module/api.py 하위호환
        "face_stability_score":    int | None,
        "face_diversity_score":    int | None,
        "posture_stability_score": int | None,
        "gaze_summary":       {...},
        "expression_summary": {...},
        "posture_summary":    {...},
        "gaze_deductions":    [...],
        "expression_deductions": [...],  # 부정적 표정이 연속 감지된 구간 (재확인용)
        "status": "success" | "partial" | "failed",
        "errors": [...],
    }
    """
    errors = []
    raw = {}

    try:
        raw.update(extract_gaze_emotion(video_path, sample_fps=sample_fps))
    except Exception as e:
        errors.append(f"gaze_emotion: {type(e).__name__}: {e}")

    try:
        raw.update(extract_posture(video_path, sample_fps=sample_fps))
    except Exception as e:
        errors.append(f"posture: {type(e).__name__}: {e}")

    gaze_summary = raw.pop("_gaze_summary", {}) or {}
    emotion_counts = raw.pop("_emotion_counts", {}) or {}
    expression_deductions = raw.pop("_expression_deductions", []) or []
    posture_deductions = raw.pop("_posture_deductions", []) or []
    posture_history_len = raw.pop("_history_len", 0) or 0

    def _nan_to_none(v):
        return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v

    # ── coarse score(하위호환) ───────────────────────────────────────────
    eye_contact_score = None
    if "gaze_center_ratio" in raw:
        eye_contact_score = _bucket(raw["gaze_center_ratio"],
                                     [(0.8, 100), (0.6, 80), (0.4, 60)])

    face_stability_score = face_diversity_score = None
    if "emo_negative_ratio" in raw:
        neg = raw["emo_negative_ratio"]
        face_stability_score = _bucket(-neg, [(-0.1, 100), (-0.25, 80), (-0.45, 60)])
    if "emo_entropy" in raw:
        # entropy 0(단조) ~ ln(8)≈2.08(완전 다양) — 적당히 다양한 쪽이 좋은 점수
        ent = raw["emo_entropy"]
        face_diversity_score = _bucket(ent, [(1.2, 100), (0.8, 80), (0.4, 60)])

    posture_stability_score = None
    if "posture_score_mean" in raw and not math.isnan(raw["posture_score_mean"]):
        posture_stability_score = _bucket(raw["posture_score_mean"],
                                           [(95, 100), (85, 80), (70, 60)])

    # ── 표정 상세 요약 (프론트엔드 ResultsDetail.jsx 하위호환 스키마) ───────────
    n_emo = sum(emotion_counts.values()) if emotion_counts else 0
    emotion_ratios = {e: round(c / n_emo, 3) for e, c in emotion_counts.items()} if n_emo else {}
    positive_ratio = sum(emotion_ratios.get(e, 0) for e in EMOTION_POSITIVE)
    negative_ratio = raw.get("emo_negative_ratio")

    if not emotion_counts:
        expr_feedback = "얼굴 미감지"
    elif negative_ratio is not None and negative_ratio >= 0.45:
        bad = ", ".join(e for e in EMOTION_NEGATIVE if emotion_ratios.get(e, 0) > 0.1)
        expr_feedback = f"부정적 표정({bad})이 자주 나타납니다. 면접 중 표정 관리에 신경 써보세요." if bad \
            else "부정적 표정이 자주 나타납니다. 면접 중 표정 관리에 신경 써보세요."
    elif positive_ratio >= 0.7:
        expr_feedback = "전반적으로 밝고 안정적인 표정을 유지하고 있습니다."
    elif emotion_ratios.get("Neutral", 0) >= 0.7:
        expr_feedback = "표정 변화가 거의 없습니다. 적절한 미소나 끄덕임으로 긍정적인 인상을 줄 수 있습니다."
    else:
        expr_feedback = "표정이 안정적으로 유지되고 있습니다."

    expression_summary = {
        "emotion_counts":   emotion_counts,
        "emotion_ratios":   emotion_ratios,
        "dominant_emotion": max(emotion_counts, key=emotion_counts.get) if emotion_counts else None,
        "positive_ratio":   round(positive_ratio, 3) if emotion_counts else None,
        "negative_ratio":   _nan_to_none(negative_ratio),
        "entropy":          _nan_to_none(raw.get("emo_entropy")),
        "stability_score":  face_stability_score,
        "diversity_score":  face_diversity_score,
        "feedback":         expr_feedback,
        "frame_count":      n_emo,
    }

    # ── 자세 상세 요약 (프론트엔드 ResultsDetail.jsx 하위호환 스키마) ───────────
    # posture_rtmpose_3d는 연속 점수(0~100)를 주므로, 기존 slouch_count/ratio는
    # "구간 점수 < 65"(analyze_posture의 감점 기준과 동일)로 재정의해 근사한다.
    slouch_count = len(posture_deductions)
    slouch_ratio = slouch_count / max(posture_history_len, 1) if posture_history_len else None

    if posture_history_len == 0:
        posture_feedback = None
    elif slouch_ratio <= 0.1:
        posture_feedback = "자세가 전반적으로 안정적입니다."
    elif slouch_ratio <= 0.3:
        posture_feedback = f"구부정한 자세가 {slouch_count}회 감지되었습니다. 허리를 펴고 어깨를 편 자세를 유지해보세요."
    else:
        posture_feedback = f"구부정한 자세가 자주 나타납니다({int(slouch_ratio*100)}%). 면접 중 바른 자세를 의식적으로 유지해보세요."

    posture_summary = {
        "score_mean":        _nan_to_none(raw.get("posture_score_mean")),
        "score_min":         _nan_to_none(raw.get("posture_score_min")),
        "pose_detect_ratio": _nan_to_none(raw.get("pose_detect_ratio")),
        "slouch_count":      slouch_count,
        "upright_count":     max(posture_history_len - slouch_count, 0),
        "slouch_ratio":      round(slouch_ratio, 3) if slouch_ratio is not None else None,
        "feedback":          posture_feedback,
    }

    scores = [eye_contact_score, face_stability_score, face_diversity_score, posture_stability_score]
    success_count = sum(1 for s in scores if s is not None)
    if success_count == 0:
        status = "failed"
    elif success_count < len(scores):
        status = "partial"
    else:
        status = "success"

    return {
        "raw_features":            {k: _nan_to_none(v) for k, v in raw.items()},
        "eye_contact_score":       eye_contact_score,
        "face_stability_score":    face_stability_score,
        "face_diversity_score":    face_diversity_score,
        "posture_stability_score": posture_stability_score,
        "gaze_summary":            gaze_summary,
        "expression_summary":      expression_summary,
        "posture_summary":         posture_summary,
        "gaze_deductions":         gaze_summary.get("deviated_segments", []),
        "expression_deductions":   expression_deductions,
        "posture_deductions":      posture_deductions,
        "status":                  status,
        "errors":                  errors,
    }
