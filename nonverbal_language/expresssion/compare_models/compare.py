import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import torch
_original_load = torch.load
torch.load = lambda *args, **kwargs: _original_load(*args, **{**kwargs, 'weights_only': False})
from hsemotion.facial_emotions import HSEmotionRecognizer
torch.load = _original_load

import torch.nn as nn
from torchvision import transforms, models
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import numpy as np
import math
import mediapipe as mp

# ── 설정 ──────────────────────────────────────────
CLASS_NAMES = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise']
DEVICE      = 'cuda' if torch.cuda.is_available() else 'cpu'
FRAMES_DIR  = '/workspace/CSM/nonverbal_language/Video to frames/frames'
DAN_CKPT    = '/workspace/CSM/nonverbal_language/expresssion/best_emotion_model_DAN.pth'
MP_MODEL    = '/workspace/CSM/nonverbal_language/face_landmarker.task'
OUTPUT_PATH = './emotion_result.jpg'
MP_DETECTOR = '/workspace/CSM/nonverbal_language/blaze_face_short_range.tflite'
MARGIN      = 0.2

HS_MAP = {'Anger': 'Anger', 'Contempt': 'Contempt', 'Disgust': 'Disgust', 'Fear': 'Fear',
          'Happiness': 'Happy', 'Neutral': 'Neutral', 'Sadness': 'Sad', 'Surprise': 'Surprise'}

val_tf = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

# ── 얼굴 크롭 ──────────────────────────────────────
def crop_face(img: Image.Image) -> Image.Image:
    options = mp.tasks.vision.FaceDetectorOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MP_DETECTOR),
        min_detection_confidence=0.3
    )
    with mp.tasks.vision.FaceDetector.create_from_options(options) as detector:
        img_rgb  = np.array(img)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        result   = detector.detect(mp_image)
    if not result.detections:
        return img
    det = result.detections[0].bounding_box
    w, h = img.size
    x1 = max(0, int(det.origin_x - MARGIN * det.width))
    y1 = max(0, int(det.origin_y - MARGIN * det.height))
    x2 = min(w, int(det.origin_x + det.width  * (1 + MARGIN)))
    y2 = min(h, int(det.origin_y + det.height * (1 + MARGIN)))
    return img.crop((x1, y1, x2, y2))

# ── DAN 모델 ──────────────────────────────────────
class AttentionHead(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, in_channels, 1)
        self.bn   = nn.BatchNorm2d(in_channels)

    def forward(self, x):
        return x * torch.sigmoid(self.bn(self.conv(x)))

class DAN(nn.Module):
    def __init__(self, num_classes=8, num_heads=4):
        super().__init__()
        resnet = models.resnet18(weights=None)
        self.backbone    = nn.Sequential(*list(resnet.children())[:-2])
        self.heads       = nn.ModuleList([AttentionHead(512) for _ in range(num_heads)])
        self.head_weight = nn.Linear(num_heads, num_heads)
        self.gap         = nn.AdaptiveAvgPool2d(1)
        self.classifier  = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512 * (num_heads + 1), 256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, num_classes)
        )
        self.num_heads = num_heads

    def forward(self, x):
        feat      = self.backbone(x)
        head_outs = [self.gap(head(feat)) for head in self.heads]
        scores    = torch.stack([h.view(h.size(0), -1).mean(dim=1) for h in head_outs], dim=1)
        weights   = torch.softmax(self.head_weight(scores), dim=1)
        weighted  = sum(w.view(-1, 1, 1, 1) * h for w, h in zip(weights.unbind(dim=1), head_outs))
        concat    = torch.cat(head_outs, dim=1)
        final     = torch.cat([concat, weighted], dim=1)
        return self.classifier(final)

# ── 모델 로드 ──────────────────────────────────────
def load_dan():
    model = DAN().to(DEVICE)
    ckpt  = torch.load(DAN_CKPT, map_location=DEVICE)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()
    return model

def load_hsemotion():
    return HSEmotionRecognizer(model_name='enet_b2_8', device='cpu')

def load_mediapipe():
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MP_MODEL),
        output_face_blendshapes=True,
        running_mode=mp.tasks.vision.RunningMode.IMAGE
    )
    return mp.tasks.vision.FaceLandmarker.create_from_options(options)

# ── 추론 함수 ──────────────────────────────────────
def predict_dan(model, img_path):
    img    = crop_face(Image.open(img_path).convert('RGB'))
    tensor = val_tf(img).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        return CLASS_NAMES[model(tensor).argmax(1).item()]

def predict_hsemotion(fer, img_path):
    try:
        img      = crop_face(Image.open(img_path).convert('RGB'))
        face_img = np.array(img)
        emotion, _ = fer.predict_emotions(face_img)
        return HS_MAP.get(emotion, emotion)
    except:
        return 'N/A'

def classify_blendshape(bs):
    smile       = (bs['mouthSmileLeft']  + bs['mouthSmileRight'])  / 2
    eye_squint  = (bs['eyeSquintLeft']   + bs['eyeSquintRight'])   / 2
    brow_down   = (bs['browDownLeft']    + bs['browDownRight'])    / 2
    mouth_frown = (bs['mouthFrownLeft']  + bs['mouthFrownRight'])  / 2
    eye_wide    = (bs['eyeWideLeft']     + bs['eyeWideRight'])     / 2

    if (smile > 0.25 and eye_squint > 0.3) or eye_squint > 0.35:
        return '기쁨(+2)'
    elif mouth_frown > 0.3 or (brow_down > 0.4 and eye_wide < 0.1):
        return '슬픔(-2)'
    else:
        return '경직(0)'

def predict_mediapipe(landmarker, img_path):
    try:
        img_rgb  = np.array(Image.open(img_path).convert('RGB'))
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        result   = landmarker.detect(mp_image)
        if not result.face_blendshapes:
            return 'N/A'
        bs = {b.category_name: b.score for b in result.face_blendshapes[0]}
        return classify_blendshape(bs)
    except:
        return 'N/A'

# ── 결과 이미지 생성 ───────────────────────────────
def make_result_image(img_paths, dan_model, hs_model, mp_landmarker):
    THUMB  = 200
    PAD    = 8
    TEXT_H = 60
    COLS   = 8
    ROWS   = math.ceil(len(img_paths) / COLS)

    cell_w = THUMB + PAD * 2
    cell_h = THUMB + TEXT_H + PAD * 2
    canvas = Image.new('RGB', (cell_w * COLS, cell_h * ROWS), (30, 30, 30))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font = ImageFont.load_default()

    for i, img_path in enumerate(img_paths):
        print(f"  처리 중 {i+1}/{len(img_paths)}: {Path(img_path).name}")

        dan_result = predict_dan(dan_model, img_path)
        hs_result  = predict_hsemotion(hs_model, img_path)
        mp_result  = predict_mediapipe(mp_landmarker, img_path)

        thumb = Image.open(img_path).convert('RGB')
        thumb.thumbnail((THUMB, THUMB))

        col = i % COLS
        row = i // COLS
        x   = col * cell_w + PAD
        y   = row * cell_h + PAD
        canvas.paste(thumb, (x, y))

        draw = ImageDraw.Draw(canvas)
        tx, ty = x, y + THUMB + 4
        draw.text((tx, ty),      f"DAN: {dan_result}", font=font, fill=(100, 200, 255))
        draw.text((tx, ty + 20), f"HS:  {hs_result}",  font=font, fill=(180, 100, 255))
        draw.text((tx, ty + 40), f"MP:  {mp_result}",  font=font, fill=(255, 150, 200))

    canvas.save(OUTPUT_PATH)
    print(f"\n[완료] 결과 저장 → {OUTPUT_PATH}")

# ── 실행 ──────────────────────────────────────────
if __name__ == "__main__":
    img_paths = sorted(Path(FRAMES_DIR).glob('*.jpg'))
    if not img_paths:
        img_paths = sorted(Path(FRAMES_DIR).glob('*.png'))
    print(f"이미지 {len(img_paths)}개 발견")

    dan_model     = load_dan()
    hs_model      = load_hsemotion()
    mp_landmarker = load_mediapipe()

    make_result_image(img_paths, dan_model, hs_model, mp_landmarker)