import cv2
import os

video_path = "/workspace/CSM/nonverbal_language/Video to frames/eye.mp4"
output_dir = "./framesss"
fps = 1

os.makedirs(output_dir, exist_ok=True)
cap = cv2.VideoCapture(video_path)
video_fps = cap.get(cv2.CAP_PROP_FPS)
interval = round(video_fps / fps)

frame_idx = 0
saved = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % interval == 0:
        cv2.imwrite(f"{output_dir}/frame_{saved:05d}.jpg", frame)
        saved += 1
    frame_idx += 1

cap.release()
print(f"완료: {saved}장 저장")