import torch
_original_load = torch.load
torch.load = lambda *args, **kwargs: _original_load(*args, **{**kwargs, 'weights_only': False})

from hsemotion.facial_emotions import HSEmotionRecognizer
torch.load = _original_load

import json
import numpy as np
from PIL import Image
from pathlib import Path
from sklearn.metrics import classification_report

CLASS_NAMES = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise']
HS_MAP = {'Anger': 0, 'Contempt': 1, 'Disgust': 2, 'Fear': 3,
          'Happiness': 4, 'Neutral': 5, 'Sadness': 6, 'Surprise': 7}

DATA_ROOT  = '/workspace/CSM/nonverbal_language/data/affectnet/archive (1)/YOLO_format'
MAX_IMAGES = 500

fer = HSEmotionRecognizer(model_name='enet_b2_8', device='cpu')

samples = []
img_dir = Path(DATA_ROOT) / 'valid' / 'images'
lbl_dir = Path(DATA_ROOT) / 'valid' / 'labels'
for img_path in sorted(img_dir.glob('*.jpg'))[:MAX_IMAGES]:
    lbl_path = lbl_dir / (img_path.stem + '.txt')
    if not lbl_path.exists():
        continue
    with open(lbl_path) as f:
        line = f.readline().strip()
        if not line:
            continue
    samples.append((img_path, int(line.split()[0])))

preds, gt = [], []
for i, (img_path, label) in enumerate(samples):
    face_img = np.array(Image.open(img_path).convert('RGB'))
    emotion, _ = fer.predict_emotions(face_img)
    preds.append(HS_MAP.get(emotion, 5))
    gt.append(label)
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(samples)}")

acc = sum(p == l for p, l in zip(preds, gt)) / len(gt)
print(f"\nHSEmotion Accuracy: {acc:.4f}")
print(classification_report(gt, preds, target_names=CLASS_NAMES, zero_division=0))

report = classification_report(gt, preds, target_names=CLASS_NAMES, zero_division=0, output_dict=True)
result = {
    "accuracy": round(acc, 4),
    "classification_report": report,
    "predictions": [
        {"image": str(samples[i][0].name), "gt": gt[i], "pred": preds[i]}
        for i in range(len(samples))
    ]
}
output_path = Path(__file__).parent / "emotion_results.json"
with open(output_path, "w") as f:
    json.dump(result, f, indent=2)
print(f"\nResults saved to {output_path}")