#!/bin/bash
# 두레에타 지표누리 수집 실행 스크립트
cd ~/everbluesea
pip install requests --break-system-packages -q
export INDEXGO_API_KEY="63B20A52S251A580"
python3 fetch_indexgo.py
echo "완료. indexgo_output/ 폴더 확인"
