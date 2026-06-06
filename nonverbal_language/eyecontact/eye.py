import cv2
import mediapipe as mp
import numpy as np
import os
import glob
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = "/workspace/CSM/nonverbal_language/face_landmarker.task"

def _create_detector():
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=False,
        num_faces=1
    )
    return vision.FaceLandmarker.create_from_options(options)

def analyze_gaze_bs(blendshapes):
    """Blendshape 기반 시선 분석"""
    bs = {b.category_name: b.score for b in blendshapes}

    # 깜빡임
    blink = (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2
    if blink > 0.5:
        return "blink"

    # 상하
    look_up   = (bs.get("eyeLookUpLeft", 0)   + bs.get("eyeLookUpRight", 0))   / 2
    look_down = (bs.get("eyeLookDownLeft", 0) + bs.get("eyeLookDownRight", 0)) / 2

    # 좌우 (eyeLookIn/Out은 각 눈 기준이라 교차 적용)
    look_left  = (bs.get("eyeLookOutRight", 0) + bs.get("eyeLookInLeft", 0))  / 2
    look_right = (bs.get("eyeLookOutLeft", 0)  + bs.get("eyeLookInRight", 0)) / 2

    scores = {
        "up":    look_up,
        "down":  look_down,
        "left":  look_left,
        "right": look_right,
    }
    max_dir   = max(scores, key=scores.get)

    max_score = scores[max_dir]

    THRESHOLD = {
        "up":    0.15,
        "down":  0.45,  # ← down은 높게 (정면에서도 기본값이 높음)
        "left":  0.25,
        "right": 0.25,
    }

    # up이 임계값을 넘으면 다른 방향보다 높아도 up 우선
    if look_up >= THRESHOLD["up"]:
        return "up"

    if max_score < THRESHOLD[max_dir]:
        return "center"
    return max_dir

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
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

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

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

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

def summarize_gaze(gaze_log):
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

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

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


def make_grid(frames_dir, out_path, gaze_log, thumb_w=200, cols=8, img_ext="*.jpg"):
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
        img = cv2.imread(f)
        if img is None:
            continue
        h, w = img.shape[:2]
        thumb_h = int(thumb_w * h / w)
        thumb = cv2.resize(img, (thumb_w, thumb_h))

        direction = direction_map.get(idx, "none")
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

    cell_h = thumbs[0].shape[0]
    rows = (len(thumbs) + cols - 1) // cols
    blank = np.zeros((cell_h, thumb_w, 3), dtype=np.uint8)
    while len(thumbs) % cols != 0:
        thumbs.append(blank)

    grid_rows = [np.hstack(thumbs[i * cols:(i + 1) * cols]) for i in range(rows)]
    grid = np.vstack(grid_rows)

    cv2.imwrite(out_path, grid)
    print(f"[완료] 그리드 저장 → {out_path}  ({len(files)}장, {cols}열 × {rows}행)")


# ============ 실행 ============
# 사용법:
#   python eye.py                          # 기본 경로
#   python eye.py /workspace/framesss      # 경로 지정
if __name__ == "__main__":
    import sys
    import json

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
    make_grid(FRAMES_DIR, GRID_PATH, gaze_log, thumb_w=200, cols=8)