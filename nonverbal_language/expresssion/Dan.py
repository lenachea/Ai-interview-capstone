import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torchvision import transforms, models
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from PIL import Image
from pathlib import Path
from collections import Counter

CLASS_NAMES = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise']

# ── 모델 ──────────────────────────────────────────
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
        resnet = models.resnet18(weights='IMAGENET1K_V1')
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
        final     = torch.cat([torch.cat(head_outs, dim=1), weighted], dim=1)
        return self.classifier(final)

# ── 데이터셋 ───────────────────────────────────────
class AffectNetYOLO(Dataset):
    def __init__(self, root, split, transform=None):
        self.transform = transform
        self.samples   = []
        img_dir = Path(root) / split / 'images'
        lbl_dir = Path(root) / split / 'labels'
        for img_path in sorted(img_dir.glob('*.jpg')):
            lbl_path = lbl_dir / (img_path.stem + '.txt')
            if not lbl_path.exists():
                continue
            with open(lbl_path) as f:
                line = f.readline().strip()
                if not line:
                    continue
            self.samples.append((img_path, int(line.split()[0])))
        print(f"[{split}] {len(self.samples)}개")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, cls_id = self.samples[idx]
        img = Image.open(img_path).convert('RGB')
        if self.transform:
            img = self.transform(img)
        return img, cls_id

# ── 설정 ──────────────────────────────────────────
DEVICE     = 'cuda' if torch.cuda.is_available() else 'cpu'
DATA_ROOT  = '/workspace/CSM/nonverbal_language/data/affectnet/archive (1)/YOLO_format'
BATCH_SIZE = 32
IMG_SIZE   = 224

train_tf = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
val_tf = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

train_ds = AffectNetYOLO(DATA_ROOT, 'train', train_tf)
val_ds   = AffectNetYOLO(DATA_ROOT, 'valid', val_tf)

sample_weights = [1.0 / Counter([s[1] for s in train_ds.samples])[s[1]] for s in train_ds.samples]
train_loader   = DataLoader(train_ds, batch_size=BATCH_SIZE,
                            sampler=WeightedRandomSampler(sample_weights, len(sample_weights)),
                            num_workers=4, pin_memory=True)
val_loader     = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=4, pin_memory=True)

model     = DAN().to(DEVICE)
criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

# ── 학습 함수 ──────────────────────────────────────
def train_stage(epochs, lr, stage_name):
    optimizer = AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr, weight_decay=1e-3)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=lr * 0.01)
    best_val_acc = 0.0

    for epoch in range(epochs):
        model.train()
        total_loss, correct = 0, 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()
            out  = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            correct    += (out.detach().argmax(1) == labels).sum().item()

        model.eval()
        val_correct = 0
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
                val_correct += (model(imgs).argmax(1) == labels).sum().item()

        scheduler.step()
        val_acc = val_correct / len(val_ds)
        print(f"[{stage_name}] Epoch {epoch+1:02d}/{epochs} | "
              f"Loss: {total_loss/len(train_loader):.4f} | "
              f"Train: {correct/len(train_ds):.3f} | Val: {val_acc:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save({'epoch': epoch, 'model_state_dict': model.state_dict(),
                        'val_acc': val_acc, 'class_names': CLASS_NAMES}, 'best_emotion_model_DAN.pth')
            print(f"  ✓ 저장 (val_acc: {val_acc:.3f})")

    return best_val_acc

# ── 학습 실행 ──────────────────────────────────────
for param in model.backbone.parameters():
    param.requires_grad = False
train_stage(5, lr=1e-3, stage_name="Stage1")

for param in model.backbone[-1].parameters():
    param.requires_grad = True
train_stage(15, lr=1e-4, stage_name="Stage2")

for param in model.parameters():
    param.requires_grad = True
best = train_stage(30, lr=1e-5, stage_name="Stage3")
print(f"\n최종 최고 Val Acc: {best:.3f}")