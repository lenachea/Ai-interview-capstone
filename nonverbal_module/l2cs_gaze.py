"""
l2cs_gaze.py
------------
L2CS-Net(ResNet50 + yaw/pitch bin 분류, Gaze360 사전학습) 기반 시선 방향 추정.

MediaPipe blendshape 방식(eye_tracker.py의 analyze_gaze_bs)은 사람/카메라 각도에 따라
정면을 봐도 특정 방향 수치가 구조적으로 높게 나오는 문제가 실측으로 확인됨
(예: 안경 쓴 사용자가 정면을 봐도 eyeLookInRight≈0.3~0.4로 계속 "right"로 오분류).
L2CS-Net은 얼굴 crop 하나로 실제 yaw/pitch 각도(도 단위)를 직접 회귀하므로
그런 개인차 없이 훨씬 안정적으로 판정할 수 있다.

체크포인트: /workspace/models/L2CSNet_gaze360.pkl (hkproj/l2cs-net, Gaze360 사전학습)
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torchvision.models as tv_models
import torchvision.transforms as T

CHECKPOINT_PATH = "/workspace/models/L2CSNet_gaze360.pkl"
NUM_BINS = 90
BIN_WIDTH = 4          # degrees per bin
ANGLE_OFFSET = 180     # bin 0 == -180deg

_TRANSFORM = T.Compose([
    T.ToPILImage(),
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class L2CS(nn.Module):
    """torchvision resnet50 백본 + yaw/pitch bin 분류 head (원본 L2CS-Net 구조, 체크포인트 키 그대로 로드)."""

    def __init__(self, num_bins: int = NUM_BINS):
        super().__init__()
        backbone = tv_models.resnet50(weights=None)
        self.conv1 = backbone.conv1
        self.bn1 = backbone.bn1
        self.relu = backbone.relu
        self.maxpool = backbone.maxpool
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4
        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc_yaw_gaze = nn.Linear(2048, num_bins)
        self.fc_pitch_gaze = nn.Linear(2048, num_bins)
        self.fc_finetune = nn.Linear(2048 + 3, 3)  # 체크포인트 호환용 — 추론에는 안 씀

    def forward(self, x):
        x = self.conv1(x); x = self.bn1(x); x = self.relu(x); x = self.maxpool(x)
        x = self.layer1(x); x = self.layer2(x); x = self.layer3(x); x = self.layer4(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        return self.fc_yaw_gaze(x), self.fc_pitch_gaze(x)


_model = None
_device = "cpu"
_idx_tensor = None


def _load_model(device: str = "cuda") -> L2CS:
    global _model, _device
    if _model is not None:
        return _model

    model = L2CS()
    state_dict = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    try:
        model = model.to(device)
        _device = device
    except Exception:
        model = model.to("cpu")
        _device = "cpu"

    _model = model
    return _model


def predict_gaze(face_crop_rgb: np.ndarray, device: str = "cuda") -> tuple[float, float]:
    """
    얼굴 crop(RGB numpy array, H×W×3) → (yaw_deg, pitch_deg).
    yaw  : 양수 = 화면 기준 오른쪽 응시, 음수 = 왼쪽
    pitch: 양수 = 아래쪽 응시,          음수 = 위쪽
    """
    global _idx_tensor
    model = _load_model(device)

    tensor = _TRANSFORM(face_crop_rgb).unsqueeze(0).to(_device)
    with torch.no_grad():
        yaw_logits, pitch_logits = model(tensor)
        yaw_probs = torch.softmax(yaw_logits, dim=1)
        pitch_probs = torch.softmax(pitch_logits, dim=1)

        if _idx_tensor is None or _idx_tensor.device != yaw_probs.device:
            _idx_tensor = torch.arange(NUM_BINS, dtype=torch.float32, device=yaw_probs.device)

        yaw_deg = (yaw_probs @ _idx_tensor).item() * BIN_WIDTH - ANGLE_OFFSET
        pitch_deg = (pitch_probs @ _idx_tensor).item() * BIN_WIDTH - ANGLE_OFFSET

    return yaw_deg, pitch_deg


def classify_direction(yaw_deg: float, pitch_deg: float,
                        yaw_threshold: float = 25.0, pitch_threshold: float = 20.0) -> str:
    """yaw/pitch 각도(도) → "center"/"left"/"right"/"up"/"down" 라벨."""
    if abs(pitch_deg) >= pitch_threshold and abs(pitch_deg) >= abs(yaw_deg):
        return "down" if pitch_deg > 0 else "up"
    if abs(yaw_deg) >= yaw_threshold:
        return "right" if yaw_deg > 0 else "left"
    return "center"
