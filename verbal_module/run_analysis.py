"""
면접 영상에서 오디오를 추출하고 언어 분석 5개 항목을 각각 JSON으로 저장.
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

VIDEO_PATH  = "/workspace/CSM/nonverbal_language/Video to frames/bad_ex.mp4"
AUDIO_PATH  = "/workspace/CSM/verbal_module/interview_audio_boosted.wav"
OUTPUT_DIR  = "/workspace/CSM/verbal_module/results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 1. 오디오 파일 확인 ───────────────────────────────────────────────────────
print("[1/7] 오디오 파일 확인 중...")
if not os.path.exists(AUDIO_PATH):
    print(f"  오디오 파일 없음 → 영상에서 추출 중...")
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(VIDEO_PATH)
    clip.audio.write_audiofile(AUDIO_PATH, fps=16000, logger=None)
    clip.close()
print(f"  → {AUDIO_PATH}")

# ── 2. Whisper 전사 ───────────────────────────────────────────────────────────
print("[2/7] Whisper 전사 중 (medium 모델, 시간이 걸릴 수 있습니다)...")
from analyzers.transcriber import load_model, transcribe_with_segments
model = load_model("medium")
full_text, words_info, segments_info = transcribe_with_segments(model, AUDIO_PATH)
print(f"  → 전사 완료: {len(words_info)}개 단어")

# ── 3. 긴 침묵 ────────────────────────────────────────────────────────────────
print("[3/7] 긴 침묵 분석 중...")
from analyzers.pause_analyzer import detect_pauses
pauses = detect_pauses(words_info, pause_threshold=2.0)
result_pauses = pauses.to_dict() if hasattr(pauses, "to_dict") else vars(pauses)
with open(f"{OUTPUT_DIR}/pause_result.json", "w", encoding="utf-8") as f:
    json.dump(result_pauses, f, indent=2, ensure_ascii=False)
print(f"  → {OUTPUT_DIR}/pause_result.json")

# ── 4. 발화 속도 ─────────────────────────────────────────────────────────────
print("[4/7] 발화 속도 분석 중...")
from analyzers.speech_rate import calc_speech_rate
speech_rate = calc_speech_rate(full_text, words_info)
result_speech = speech_rate.to_dict() if hasattr(speech_rate, "to_dict") else vars(speech_rate)
with open(f"{OUTPUT_DIR}/speech_rate_result.json", "w", encoding="utf-8") as f:
    json.dump(result_speech, f, indent=2, ensure_ascii=False)
print(f"  → {OUTPUT_DIR}/speech_rate_result.json")

# ── 5. 습관어 (filler) ───────────────────────────────────────────────────────
print("[5/7] 습관어 분석 중...")
from konlpy.tag import Okt
from ngram_model import NgramLanguageModel, make_tokenizer
from filler_detector import FillerDetector
from analyzers.filler_analyzer import detect_fillers

okt = Okt()
tokenize_fn, tagger = make_tokenizer(analyzer="okt", use_pos=False)
lm = NgramLanguageModel(n=3, k=0.1, tokenize_fn=tokenize_fn)
lm.train([
    "저는 개발자입니다", "오늘 날씨가 정말 좋네요",
    "프로젝트 일정을 다시 검토해야 합니다",
    "어 오늘 음 날씨가 좋네요", "그 뭐 저 일정이 어 변경되었습니다",
])
detector = FillerDetector(lm=lm, tagger=tagger, threshold=0.35)
fillers = detect_fillers(full_text, words_info, detector)
result_fillers = fillers.to_dict() if hasattr(fillers, "to_dict") else vars(fillers)
with open(f"{OUTPUT_DIR}/filler_result.json", "w", encoding="utf-8") as f:
    json.dump(result_fillers, f, indent=2, ensure_ascii=False)
print(f"  → {OUTPUT_DIR}/filler_result.json")

# ── 6. 말 더듬음 ─────────────────────────────────────────────────────────────
print("[6/7] 말 더듬음 분석 중...")
from analyzers.stutter_analyzer import detect_stutters
stutters = detect_stutters(words_info, okt, window_size=3, time_limit=5.0)
result_stutters = stutters.to_dict() if hasattr(stutters, "to_dict") else vars(stutters)
with open(f"{OUTPUT_DIR}/stutter_result.json", "w", encoding="utf-8") as f:
    json.dump(result_stutters, f, indent=2, ensure_ascii=False)
print(f"  → {OUTPUT_DIR}/stutter_result.json")

# ── 7. 음량 안정성 ────────────────────────────────────────────────────────────
print("[7/7] 음량 안정성 분석 중...")
from analyzers.prosody_analyzer import analyze_volume
volume = analyze_volume(AUDIO_PATH, interviewee_segments=[])
with open(f"{OUTPUT_DIR}/volume_result.json", "w", encoding="utf-8") as f:
    json.dump(volume, f, indent=2, ensure_ascii=False)
print(f"  → {OUTPUT_DIR}/volume_result.json")

print("\n완료! 전사 텍스트:")
print(full_text[:300], "..." if len(full_text) > 300 else "")
