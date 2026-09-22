"""
emotion_classifier.py
---------------------
HSEmotion 기반 표정 분석 모듈.
프레임 디렉토리를 받아 감정 분포와 안정성/다양성 지표를 반환합니다.
"""
import os
import glob
import numpy as np
from pathlib import Path

_fer = None

POSITIVE_EMOTIONS = {"Happy", "Neutral", "Surprise"}
NEGATIVE_EMOTIONS = {"Anger", "Contempt", "Disgust", "Fear", "Sad"}
ALL_EMOTIONS = ["Anger", "Contempt", "Disgust", "Fear", "Happy", "Neutral", "Sad", "Surprise"]


def _load_model():
    global _fer
    if _fer is not None:
        return _fer

    import torch
    import torch.serialization

    # timm EfficientNet 글로벌 허용 (PyTorch 2.6+ weights_only=True 기본값 대응)
    try:
        import timm.models.efficientnet
        torch.serialization.add_safe_globals([timm.models.efficientnet.EfficientNet])
    except Exception:
        pass

    # weights_only=False + map_location=cpu 강제 패치
    _original_load = torch.load
    def _patched_load(*args, **kwargs):
        kwargs["weights_only"] = False
        if "map_location" not in kwargs:
            kwargs["map_location"] = torch.device("cpu")
        return _original_load(*args, **kwargs)
    torch.load = _patched_load

    try:
        from hsemotion.facial_emotions import HSEmotionRecognizer
        _fer = HSEmotionRecognizer(model_name="enet_b2_8", device="cpu")
    finally:
        torch.load = _original_load

    return _fer


def analyze_expression_frames(frames_dir: str, img_ext: str = "*.jpg") -> dict:
    """
    프레임 디렉토리를 분석해 표정 요약 반환.

    Returns
    -------
    {
        "emotion_counts":    {"Happy": 3, "Neutral": 10, ...},
        "emotion_ratios":    {"Happy": 0.23, ...},
        "dominant_emotion":  "Neutral",
        "positive_ratio":    0.65,
        "stability_score":   int (0~100),   # 부정 표정 비율 기반
        "diversity_score":   int (0~100),   # 감정 다양성 기반
        "feedback":          str,
        "frame_count":       int,
    }
    """
    frame_files = sorted(glob.glob(os.path.join(frames_dir, img_ext)))
    if not frame_files:
        frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frame_files:
        return _empty_result("프레임 없음")

    fer = _load_model()

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    # blaze_face_short_range.tflite — buffer로 로드해 한글 경로 문제 우회
    _model_path = Path(__file__).resolve().parent / "blaze_face_short_range.tflite"
    with open(_model_path, "rb") as _f:
        _model_bytes = _f.read()
    _base_opts = mp_python.BaseOptions(model_asset_buffer=_model_bytes)
    _fd_opts   = mp_vision.FaceDetectorOptions(
        base_options=_base_opts,
        min_detection_confidence=0.3,
    )
    face_detector = mp_vision.FaceDetector.create_from_options(_fd_opts)

    emotion_counts = {e: 0 for e in ALL_EMOTIONS}
    analyzed = 0

    for frame_path in frame_files:
        try:
            frame_bgr = cv2.imdecode(np.fromfile(frame_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame_bgr is None:
                continue
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]

            mp_img    = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            detections = face_detector.detect(mp_img).detections
            if not detections:
                continue

            bb = detections[0].bounding_box
            x1 = max(0, bb.origin_x)
            y1 = max(0, bb.origin_y)
            x2 = min(w, bb.origin_x + bb.width)
            y2 = min(h, bb.origin_y + bb.height)
            if x2 <= x1 or y2 <= y1:
                continue

            face_crop = frame_rgb[y1:y2, x1:x2]
            emotion, _ = fer.predict_emotions(face_crop)
            if emotion in emotion_counts:
                emotion_counts[emotion] += 1
                analyzed += 1
        except Exception as _e:
            print(f"[Expression] 프레임 오류: {_e}")
            continue

    face_detector.close()

    if analyzed == 0:
        return _empty_result("얼굴 미감지")

    emotion_ratios = {e: round(c / analyzed, 3) for e, c in emotion_counts.items()}
    dominant = max(emotion_counts, key=emotion_counts.get)

    positive_ratio = sum(emotion_ratios[e] for e in POSITIVE_EMOTIONS)
    negative_ratio = sum(emotion_ratios[e] for e in NEGATIVE_EMOTIONS)

    # 표정 안정성: 부정 표정 비율이 낮을수록 높음
    if negative_ratio <= 0.1:
        stability_score = 100
    elif negative_ratio <= 0.25:
        stability_score = 80
    elif negative_ratio <= 0.45:
        stability_score = 60
    else:
        stability_score = 40

    # 표정 다양성: 엔트로피 기반 (감정 고르게 분포할수록 높음, 단 긍정 감정 위주일 때 보너스)
    ratios = np.array(list(emotion_ratios.values()))
    ratios = ratios[ratios > 0]
    entropy = float(-np.sum(ratios * np.log(ratios + 1e-9)))
    max_entropy = np.log(len(ALL_EMOTIONS))
    diversity_normalized = entropy / max_entropy  # 0~1

    # 너무 단조롭거나(Neutral만) 너무 분산되면 낮게
    if positive_ratio >= 0.5 and diversity_normalized >= 0.4:
        diversity_score = 100
    elif positive_ratio >= 0.35 and diversity_normalized >= 0.25:
        diversity_score = 80
    elif diversity_normalized >= 0.15:
        diversity_score = 60
    else:
        diversity_score = 40

    # 피드백
    if negative_ratio >= 0.45:
        feedback = f"부정적 표정({', '.join(e for e in NEGATIVE_EMOTIONS if emotion_ratios.get(e,0) > 0.1)})이 자주 나타납니다. 면접 중 표정 관리에 신경 써보세요."
    elif positive_ratio >= 0.7:
        feedback = "전반적으로 밝고 안정적인 표정을 유지하고 있습니다."
    elif emotion_ratios.get("Neutral", 0) >= 0.7:
        feedback = "표정 변화가 거의 없습니다. 적절한 미소나 끄덕임으로 긍정적인 인상을 줄 수 있습니다."
    else:
        feedback = "표정이 안정적으로 유지되고 있습니다."

    return {
        "emotion_counts":  emotion_counts,
        "emotion_ratios":  emotion_ratios,
        "dominant_emotion": dominant,
        "positive_ratio":  round(positive_ratio, 3),
        "stability_score": stability_score,
        "diversity_score": diversity_score,
        "feedback":        feedback,
        "frame_count":     analyzed,
    }


def _empty_result(reason: str) -> dict:
    return {
        "emotion_counts":   {e: 0 for e in ALL_EMOTIONS},
        "emotion_ratios":   {e: 0.0 for e in ALL_EMOTIONS},
        "dominant_emotion": "Neutral",
        "positive_ratio":  0.0,
        "stability_score": None,
        "diversity_score": None,
        "feedback":        reason,
        "frame_count":     0,
    }
