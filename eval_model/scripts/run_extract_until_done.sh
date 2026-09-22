#!/bin/bash
# ONNX Runtime이 간헐적으로 프로세스를 죽여서, 36개가 다 나올 때까지 재시도한다.
# extract_features.py 는 완료된 영상을 건너뛰므로 재실행 비용은 크래시 직전 1개뿐.
cd /workspace/CSM/eval_model/scripts
export LD_LIBRARY_PATH=/opt/conda/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/conda/lib:$LD_LIBRARY_PATH
FEAT_DIR=/workspace/CSM/eval_model/data/features

for attempt in $(seq 1 20); do
  n=$(ls "$FEAT_DIR" | wc -l)
  if [ "$n" -ge 36 ]; then
    echo "=== 전체 36개 완료 (시도 $attempt회차 시작 전) ==="
    exit 0
  fi
  echo "=== 시도 $attempt: 현재 $n/36 ==="
  python3 extract_features.py --sample-fps 2
  sleep 3
done
echo "=== 20회 시도 후 종료: $(ls "$FEAT_DIR" | wc -l)/36 ==="
