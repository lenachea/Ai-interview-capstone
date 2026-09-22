#!/bin/bash
# 추출 36개 완료를 기다렸다가 데이터셋 병합 → 모델 비교까지 이어서 실행
cd /workspace/CSM/eval_model/scripts
FEAT_DIR=/workspace/CSM/eval_model/data/features

echo "=== 추출 완료 대기 중 ==="
while [ "$(ls $FEAT_DIR | wc -l)" -lt 36 ]; do sleep 30; done
echo "=== 추출 36개 완료, 학습 시작 $(date +%H:%M:%S) ==="

# 소규모 데이터에서 BLAS/OpenMP 스레드 폭주 방지
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
export MKL_NUM_THREADS=4

python3 build_dataset.py 2>&1 | grep -v "NumPy 1.x\|pybind11\|downgrade\|We expect"
echo "=== 데이터셋 병합 완료, 모델 비교 시작 $(date +%H:%M:%S) ==="
python3 compare_models.py 2>&1 | grep -v "NumPy 1.x\|pybind11\|downgrade\|We expect"
echo "=== 전체 완료 $(date +%H:%M:%S) ==="
