import cv2
import mediapipe as mp
import numpy as np
import os
from pathlib import Path
import glob
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = str((Path(__file__).resolve().parent / "face_landmarker.task"))
FACE_CROP_PADDING = 0.25

def _create_detector():
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=False,
        num_faces=1
    )


    return vision.FaceLandmarker.create_from_options(options)

def detect_cropped_face(frame, detector, padding=FACE_CROP_PADDING):
    """전체 프레임에서 얼굴을 찾은 뒤 여백을 두고 크롭하여 다시 분석한다."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    initial_result = detector.detect(mp_image)

    if not initial_result.face_landmarks:
        return frame, initial_result

    h, w = frame.shape[:2]
    landmarks = initial_result.face_landmarks[0]
    xs = [landmark.x * w for landmark in landmarks]
    ys = [landmark.y * h for landmark in landmarks]

    face_w = max(xs) - min(xs)
    face_h = max(ys) - min(ys)
    pad_x = face_w * padding
    pad_y = face_h * padding

    x1 = max(0, int(min(xs) - pad_x))
    y1 = max(0, int(min(ys) - pad_y))
    x2 = min(w, int(max(xs) + pad_x))
    y2 = min(h, int(max(ys) + pad_y))

    if x2 <= x1 or y2 <= y1:
        return frame, initial_result

    cropped = frame[y1:y2, x1:x2].copy()
    crop_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    crop_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
    crop_result = detector.detect(crop_image)

    if not crop_result.face_landmarks:
        return frame, initial_result
    return cropped, crop_result

def gaze_signals(blendshapes):
    """
    blendshape → {up, down, left, right, blink} 원본 신호(0~1 근처).
    분류(threshold) 없이 순수 신호만 반환 — baseline 보정(calibrate_gaze_log)에 사용.
    """
    bs = {b.category_name: b.score for b in blendshapes}
    return {
        "up":    (bs.get("eyeLookUpLeft", 0)   + bs.get("eyeLookUpRight", 0))   / 2,
        "down":  (bs.get("eyeLookDownLeft", 0) + bs.get("eyeLookDownRight", 0)) / 2,
        # 좌우: eyeLookIn/Out은 각 눈 기준이라 교차 적용
        "left":  (bs.get("eyeLookOutRight", 0) + bs.get("eyeLookInLeft", 0))  / 2,
        "right": (bs.get("eyeLookOutLeft", 0)  + bs.get("eyeLookInRight", 0)) / 2,
        "blink": (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2,
    }


def analyze_gaze_bs(blendshapes):
    """
    Blendshape 기반 시선 분석 (절대 threshold, baseline 보정 없음).

    ⚠️ 사람마다/카메라 각도마다 정면을 봐도 특정 방향의 기본값이 높게 나올 수 있음
    (예: 안경 쓴 사람은 정면에서도 eyeLookInRight가 0.3~0.4로 높게 나와 계속 "right"로
    잘못 분류되는 경우 실측 확인됨). 라이브 분석(vision_features.py)은 이 함수 대신
    calibrate_gaze_log()로 영상 전체의 baseline을 잡고 상대적으로 판정한다.
    이 함수는 프레임 1장만 볼 수 있는 기존 호출부(하위호환)용으로 남겨둔다.
    """
    signals = gaze_signals(blendshapes)

    if signals["blink"] > 0.5:
        return "blink"

    THRESHOLD = {
        "up":    0.15,
        "down":  0.45,  # ← down은 높게 (정면에서도 기본값이 높음)
        "left":  0.25,
        "right": 0.25,
    }

    max_dir = max(("up", "down", "left", "right"), key=lambda k: signals[k])
    max_score = signals[max_dir]

    # up이 임계값을 넘으면 다른 방향보다 높아도 up 우선
    if signals["up"] >= THRESHOLD["up"]:
        return "up"

    if max_score < THRESHOLD[max_dir]:
        return "center"
    return max_dir


def calibrate_gaze_log(timed_signals, threshold=0.15, blink_threshold=0.5):
    """
    프레임별 gaze_signals()를 모아, 영상 전체의 중앙값을 "정면 baseline"으로 잡고
    거기서 벗어난 정도로 방향을 재분류한다.

    Parameters
    ----------
    timed_signals : list[(time, signals_dict)]
        gaze_signals()의 시간별 기록 (깜빡임 프레임도 포함해서 넘기면 됨 — 여기서 제외 처리).
    threshold : float
        baseline 대비 이 값 이상 벗어나야 해당 방향으로 판정 (모든 방향 동일 적용).

    Returns
    -------
    list[{"time": float, "direction": str}]
        analyze_frames_gaze()가 만들던 gaze_log와 동일한 형태.
    """
    axes = ("up", "down", "left", "right")
    non_blink = [s for _, s in timed_signals if s["blink"] <= blink_threshold]

    if not non_blink:
        baseline = {k: 0.0 for k in axes}
    else:
        baseline = {
            k: float(np.median([s[k] for s in non_blink]))
            for k in axes
        }

    gaze_log = []
    for t, s in timed_signals:
        if s["blink"] > blink_threshold:
            gaze_log.append({"time": t, "direction": "blink"})
            continue

        adjusted = {k: max(0.0, s[k] - baseline[k]) for k in axes}
        max_dir = max(axes, key=lambda k: adjusted[k])

        direction = max_dir if adjusted[max_dir] >= threshold else "center"
        gaze_log.append({"time": t, "direction": direction})

    return gaze_log

def analyze_video_gaze(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 30
    gaze_log = []
    detector = _create_detector()
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_time = frame_idx / fps
        _, result = detect_cropped_face(frame, detector)

        if result.face_landmarks and result.face_blendshapes:
            direction = analyze_gaze_bs(result.face_blendshapes[0])
            gaze_log.append({
                "time": round(current_time, 2),
                "direction": direction
            })

        frame_idx += 1

    cap.release()
    return gaze_log

def analyze_frames_gaze(frames_dir, fps=30, img_ext="*.jpg"):
    frame_files = sorted(glob.glob(os.path.join(frames_dir, img_ext)))
    if not frame_files:
        frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frame_files:
        print(f"[ERROR] 프레임 이미지를 찾을 수 없습니다: {frames_dir}")
        return []

    print(f"[INFO] 총 {len(frame_files)}개 프레임 발견")

    detector = _create_detector()
    gaze_log = []

    for frame_idx, frame_path in enumerate(frame_files):
        current_time = round(frame_idx / fps, 2)

        frame = cv2.imread(frame_path)
        if frame is None:
            print(f"[WARN] 읽기 실패: {frame_path}")
            continue

        _, result = detect_cropped_face(frame, detector)

        if result.face_landmarks and result.face_blendshapes:
            bs = {b.category_name: b.score for b in result.face_blendshapes[0]}
            direction = analyze_gaze_bs(result.face_blendshapes[0])
            gaze_log.append({
                "time": current_time,
                "direction": direction,
                "scores": {
                    "U": round((bs.get("eyeLookUpLeft", 0)    + bs.get("eyeLookUpRight", 0))   / 2, 3),
                    "D": round((bs.get("eyeLookDownLeft", 0)  + bs.get("eyeLookDownRight", 0)) / 2, 3),
                    "L": round((bs.get("eyeLookOutRight", 0)  + bs.get("eyeLookInLeft", 0))    / 2, 3),
                    "R": round((bs.get("eyeLookOutLeft", 0)   + bs.get("eyeLookInRight", 0))   / 2, 3),
                }
            })
        else:
            print(f"[WARN] 얼굴 미감지: {os.path.basename(frame_path)} (t={current_time}s)")

    return gaze_log

def summarize_gaze(gaze_log, min_blink_duration=0.6):
    """
    min_blink_duration : 초. 이보다 짧은 "blink" 구간은 정상적인 눈 깜빡임으로 보고
        deviated_segments(타임라인/감점 구간)에서 제외한다. 여러 프레임에 걸쳐
        연속으로 감지된(=일정 시간 이상 눈을 감고 있거나 실눈을 뜬) 경우만 문제로 본다.
        left/right/up/down 이탈은 그대로 전부 포함(짧아도 의미 있는 신호).
    """
    total = len(gaze_log)
    if total == 0:
        return {}

    directions = ["left", "right", "up", "down", "blink"]
    center_count = sum(1 for g in gaze_log if g["direction"] == "center")
    center_ratio = center_count / total

    direction_counts = {d: sum(1 for g in gaze_log if g["direction"] == d) for d in directions}
    direction_ratios = {d: round(c / total, 2) for d, c in direction_counts.items()}

    deviated_segments = []
    seg_start = None

    for i, g in enumerate(gaze_log):
        if g["direction"] != "center" and seg_start is None:
            seg_start = g["time"]
        elif g["direction"] == "center" and seg_start is not None:
            deviated_segments.append({
                "start": seg_start,
                "end": gaze_log[i - 1]["time"],
                "direction": gaze_log[i - 1]["direction"]
            })
            seg_start = None

    if seg_start is not None:
        deviated_segments.append({
            "start": seg_start,
            "end": gaze_log[-1]["time"],
            "direction": gaze_log[-1]["direction"]
        })

    deviated_segments = [
        s for s in deviated_segments
        if not (s["direction"] == "blink" and (s["end"] - s["start"]) < min_blink_duration)
    ]

    if center_ratio >= 0.8:
        feedback = "시선 처리 안정적"
    elif center_ratio >= 0.6:
        feedback = "가끔 시선 이탈"
    else:
        feedback = "시선 회피 빈번 — 자신감 부족으로 보일 수 있음"

    return {
        "gaze_ratio": round(center_ratio, 2),
        "direction_ratios": direction_ratios,
        "feedback": feedback,
        "deviated_segments": deviated_segments
    }


def visualize_gaze_frames(frames_dir, output_dir, fps=1, img_ext="*.jpg"):
    os.makedirs(output_dir, exist_ok=True)
    frame_files = sorted(glob.glob(os.path.join(frames_dir, img_ext)))
    if not frame_files:
        frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frame_files:
        print(f"[ERROR] 프레임 없음: {frames_dir}")
        return

    detector = _create_detector()
    DIR_COLOR = {
        "center": (0, 200, 0),
        "left":   (0, 0, 220),
        "right":  (220, 100, 0),
        "up":     (220, 0, 220),
        "down":   (0, 220, 220),
        "blink":  (150, 150, 150),
    }

    EYE_CORNERS = [(33, 133), (362, 263)]
    IRIS_IDX    = [468, 473]

    for frame_path in frame_files:
        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        frame, result = detect_cropped_face(frame, detector)
        h, w = frame.shape[:2]

        if result.face_landmarks and result.face_blendshapes:
            lm = result.face_landmarks[0]
            bs = {b.category_name: b.score for b in result.face_blendshapes[0]}

            direction = analyze_gaze_bs(result.face_blendshapes[0])
            color = DIR_COLOR[direction]

            up    = (bs.get("eyeLookUpLeft", 0)    + bs.get("eyeLookUpRight", 0))   / 2
            down  = (bs.get("eyeLookDownLeft", 0)  + bs.get("eyeLookDownRight", 0)) / 2
            left  = (bs.get("eyeLookOutRight", 0)  + bs.get("eyeLookInLeft", 0))    / 2
            right = (bs.get("eyeLookOutLeft", 0)   + bs.get("eyeLookInRight", 0))   / 2

            # 눈꼬리 연결선
            for outer, inner in EYE_CORNERS:
                p1 = (int(lm[outer].x * w), int(lm[outer].y * h))
                p2 = (int(lm[inner].x * w), int(lm[inner].y * h))
                cv2.line(frame, p1, p2, (200, 200, 200), 1)
                cv2.circle(frame, p1, 3, (200, 200, 200), -1)
                cv2.circle(frame, p2, 3, (200, 200, 200), -1)

            # 홍채 중심
            for iris_idx in IRIS_IDX:
                px = int(lm[iris_idx].x * w)
                py = int(lm[iris_idx].y * h)
                cv2.circle(frame, (px, py), 5, color, -1)

            # 상단 텍스트
            label = f"{direction.upper()}  (thr=0.25)"
            cv2.rectangle(frame, (0, 0), (w, 36), (30, 30, 30), -1)
            cv2.putText(frame, label, (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

            # 하단 방향별 점수 막대그래프
            bar_scores = [
                ("U", up,    (220, 0, 220)),
                ("D", down,  (0, 220, 220)),
                ("L", left,  (0, 0, 220)),
                ("R", right, (220, 100, 0)),
            ]
            bar_h     = 28          # 막대 높이
            label_w   = 22          # 라벨("U" 등) 너비
            bar_area  = w - label_w * len(bar_scores)
            bar_unit  = bar_area // len(bar_scores)
            y_base    = h - bar_h

            # 배경
            cv2.rectangle(frame, (0, y_base), (w, h), (30, 30, 30), -1)

            for i, (tag, score, bcolor) in enumerate(bar_scores):
                x_label = i * (label_w + bar_unit)
                x_bar   = x_label + label_w
                bar_len = int(bar_unit * min(score, 1.0))

                # 라벨
                cv2.putText(frame, tag, (x_label + 3, h - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                # 막대 배경
                cv2.rectangle(frame, (x_bar, y_base + 4), (x_bar + bar_unit, h - 4), (70, 70, 70), -1)
                # 막대 채우기
                if bar_len > 0:
                    # 임계값(0.25) 초과 시 밝게
                    fill_color = bcolor if score >= 0.25 else tuple(c // 2 for c in bcolor)
                    cv2.rectangle(frame, (x_bar, y_base + 4), (x_bar + bar_len, h - 4), fill_color, -1)
                # 점수 숫자
                cv2.putText(frame, f"{score:.2f}", (x_bar + 2, h - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

        else:
            cv2.rectangle(frame, (0, 0), (w, 36), (30, 30, 30), -1)
            cv2.putText(frame, "NO FACE", (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)

        out_path = os.path.join(output_dir, os.path.basename(frame_path))
        cv2.imwrite(out_path, frame)

    print(f"[완료] {len(frame_files)}장 저장 → {output_dir}")


def make_grid(frames_dir, out_path, gaze_log, thumb_w=200, cols=8, img_ext="*.jpg", only_non_center=False):
    DIR_COLOR = {
        "center": (0, 200, 0),
        "left":   (0, 0, 220),
        "right":  (220, 100, 0),
        "up":     (220, 0, 220),
        "down":   (0, 220, 220),
        "blink":  (150, 150, 150),
        "none":   (80, 80, 80),
    }
    SCORE_COLOR = {
        "U": (220, 0, 220),
        "D": (0, 220, 220),
        "L": (0, 0, 220),
        "R": (220, 100, 0),
    }
    LABEL_H  = 24   # 방향 텍스트 행
    SCORE_H  = 20   # 점수 바 행

    files = sorted(glob.glob(os.path.join(frames_dir, img_ext)))
    if not files:
        files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not files:
        print("[ERROR] 그리드 만들 이미지 없음")
        return

    direction_map = {i: g["direction"] for i, g in enumerate(gaze_log)}
    scores_map    = {i: g.get("scores", {}) for i, g in enumerate(gaze_log)}

    thumbs = []
    for idx, f in enumerate(files):
        direction = direction_map.get(idx, "none")
        if only_non_center and direction == "center":
            continue
        img = cv2.imread(f)
        if img is None:
            continue
        h, w = img.shape[:2]
        thumb_h = int(thumb_w * 1.25)
        scale = min(thumb_w / w, thumb_h / h)
        resized_w = max(1, int(w * scale))
        resized_h = max(1, int(h * scale))
        resized = cv2.resize(img, (resized_w, resized_h))
        thumb = np.zeros((thumb_h, thumb_w, 3), dtype=np.uint8)
        offset_x = (thumb_w - resized_w) // 2
        offset_y = (thumb_h - resized_h) // 2
        thumb[offset_y:offset_y + resized_h, offset_x:offset_x + resized_w] = resized

        color     = DIR_COLOR[direction]
        scores    = scores_map.get(idx, {})

        cv2.rectangle(thumb, (0, 0), (thumb_w - 1, thumb_h - 1), color, 4)

        # 1행: 방향 라벨
        label_bar = np.zeros((LABEL_H, thumb_w, 3), dtype=np.uint8)
        label_bar[:] = color
        text = f"#{idx}  {direction.upper()}"
        cv2.putText(label_bar, text, (4, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)

        # 2행: U/D/L/R 점수 미니 바
        score_bar = np.zeros((SCORE_H, thumb_w, 3), dtype=np.uint8)
        score_bar[:] = (25, 25, 25)
        tags = ["U", "D", "L", "R"]
        seg_w = thumb_w // len(tags)
        for si, tag in enumerate(tags):
            val = scores.get(tag, 0)
            sx  = si * seg_w
            # 태그 텍스트
            cv2.putText(score_bar, tag, (sx + 2, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)
            # 점수 바
            bar_x  = sx + 14
            bar_max = seg_w - 16
            bar_len = int(bar_max * min(val, 1.0))
            cv2.rectangle(score_bar, (bar_x, 4), (bar_x + bar_max, SCORE_H - 4), (60, 60, 60), -1)
            if bar_len > 0:
                bc = SCORE_COLOR[tag] if val >= 0.25 else tuple(c // 3 for c in SCORE_COLOR[tag])
                cv2.rectangle(score_bar, (bar_x, 4), (bar_x + bar_len, SCORE_H - 4), bc, -1)
            # 점수 숫자
            cv2.putText(score_bar, f"{val:.2f}", (bar_x + 1, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (220, 220, 220), 1)

        cell = np.vstack([thumb, label_bar, score_bar])
        thumbs.append(cell)

    if not thumbs:
        print("[INFO] center가 아닌 프레임이 없습니다.")
        return

    selected_count = len(thumbs)
    cell_h = thumbs[0].shape[0]
    rows = (len(thumbs) + cols - 1) // cols
    blank = np.zeros((cell_h, thumb_w, 3), dtype=np.uint8)
    while len(thumbs) % cols != 0:
        thumbs.append(blank)

    grid_rows = [np.hstack(thumbs[i * cols:(i + 1) * cols]) for i in range(rows)]
    grid = np.vstack(grid_rows)

    cv2.imwrite(out_path, grid)
    print(f"[완료] 그리드 저장 → {out_path}  ({selected_count}장, {cols}열 × {rows}행)")


# ============ 실행 ============
# 사용법:
#   python eye.py                          # 기본 경로
#   python eye.py /workspace/framesss      # 경로 지정
if __name__ == "__main__":
    import sys
    import json
    import subprocess

    if len(sys.argv) == 1:
        frames_script = "/workspace/CSM/nonverbal_language/Video to frames/frames_cut.py"
        print("선택한 동영상에서 프레임을 생성합니다...")
        subprocess.run([sys.executable, frames_script], check=True)

    FRAMES_DIR = sys.argv[1] if len(sys.argv) > 1 else "/workspace/CSM/nonverbal_language/Video to frames/frames"
    VIZ_DIR    = os.path.join(FRAMES_DIR, "../frames_viz")
    GRID_PATH  = os.path.join(FRAMES_DIR, "../gaze_grid.jpg")
    JSON_PATH  = os.path.join(FRAMES_DIR, "../gaze_results.json")

    gaze_log = analyze_frames_gaze(FRAMES_DIR, fps=1)
    result   = summarize_gaze(gaze_log)

    print(f"\n분석된 프레임 수: {len(gaze_log)}")
    print(f"시선 중앙 비율:   {result.get('gaze_ratio', 0) * 100:.1f}%")
    ratios = result.get("direction_ratios", {})
    print(f"방향별 비율:      좌={ratios.get('left',0)*100:.1f}%  우={ratios.get('right',0)*100:.1f}%  위={ratios.get('up',0)*100:.1f}%  아래={ratios.get('down',0)*100:.1f}%  깜빡임={ratios.get('blink',0)*100:.1f}%")
    print(f"피드백:           {result.get('feedback', '')}")
    print(f"\n이탈 구간 ({len(result.get('deviated_segments', []))}개):")
    for seg in result.get("deviated_segments", []):
        print(f"  {seg['start']}s ~ {seg['end']}s → {seg['direction']}")

    json_output = {
        "summary": result,
        "gaze_log": gaze_log
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {JSON_PATH}")

    print("\n시각화 저장 중...")
    visualize_gaze_frames(FRAMES_DIR, VIZ_DIR, fps=1)

    print("그리드 생성 중...")
    make_grid(VIZ_DIR, GRID_PATH, gaze_log, thumb_w=200, cols=8)