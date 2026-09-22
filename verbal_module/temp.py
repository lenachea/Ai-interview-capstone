# 임계값 탐색용 임시 스크립트
import librosa
import numpy as np

files = [
    "data\wavs\ckmk_a_ict_f_e_156000.wav",
    "data\wavs\ckmk_a_ict_f_e_156001.wav",
    "data\wavs\ckmk_a_ict_f_e_156002.wav",
    "data\wavs\ckmk_a_ict_f_e_158683.wav",
    "data\wavs\ckmk_a_ict_f_e_158684.wav",
    "data\wavs\ckmk_a_ict_f_e_158685.wav",
    "data\wavs\ckmk_a_ict_f_e_158686.wav",
    "data\wavs\ckmk_a_ict_f_e_158687.wav",
    "data\wavs\ckmk_a_ict_f_e_158688.wav",
    "data\wavs\ckmk_a_ict_f_e_158689.wav",
    "data\wavs\ckmk_a_ict_f_e_158690.wav",
    "data\wavs\ckmk_a_ict_f_e_158691.wav",
    "data\wavs\ckmk_a_ict_f_e_158692.wav",
    "data\wavs\ckmk_a_ict_f_e_161363.wav",
    "data\wavs\ckmk_a_ict_f_e_161364.wav",
    "data\wavs\ckmk_a_ict_f_e_161365.wav",
    "data\wavs\ckmk_a_ict_f_e_161366.wav",
    "data\wavs\ckmk_a_ict_f_e_161367.wav",
    "data\wavs\ckmk_a_ict_f_e_161368.wav",
    "data\wavs\ckmk_a_ict_f_e_161369.wav",
    "data\wavs\ckmk_a_ict_f_e_161370.wav"
]

for path in files:
    y, sr = librosa.load(path, sr=None, mono=True)
    rms = librosa.feature.rms(y=y)[0]
    rms_active = rms[rms > 0.001]
    cv = float(np.std(rms_active) / np.mean(rms_active))
    print(f"{path}: cv={cv:.3f}, mean={np.mean(rms_active):.4f}")