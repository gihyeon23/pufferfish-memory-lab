# 증거 자료: swap이 128MiB보다 더 필요했는지 직접 검증

## 질문

"로그에 `swap=127.9MiB`로 찍힌 게, 진짜 그만큼만 필요했던 건지, 아니면
128MiB 상한(`SWAP_HEADROOM_MB`)에 막혀서 그렇게 보이기만 하는 건지
어떻게 아는가?"

## 실험 방법

`SWAP_HEADROOM_MB`(swap 상한, 원래 128MiB)를 **일시적으로 512MiB로
늘려서**, 같은 워크로드를 다시 돌렸을 때 swap이 128MiB를 넘어가는지
확인했다. 넘어간다면 "원래 128MiB는 진짜 수요가 아니라 상한에 잘린
값이었다"는 직접 증명이 된다.

```python
# controller/puff_manager.py, 일시적으로 변경 (실험 후 원상복구함)
SWAP_HEADROOM_MB = 128  ->  SWAP_HEADROOM_MB = 512
```

```bash
docker run -d --name pf-swap-1 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest
docker run -d --name pf-swap-2 (동일 설정)
python3 container_monitor.py pf-swap-1 --interval 0.5 > swap-exp-1.log &
python3 container_monitor.py pf-swap-2 --interval 0.5 > swap-exp-2.log &
```

## 결과 — swap이 128MiB를 확실히 넘어감

| 경과 시간 | `pf-swap-1` swap | `pf-swap-2` swap |
|---|---|---|
| 50s | 44.5MiB | 82.1MiB |
| 80s | 155.7MiB | 115.5MiB |
| 90s | 179.0MiB | 182.6MiB |
| 120s | 183.2MiB | 190.8MiB |
| 200s (안정화) | **183.2MiB** | **190.8MiB** |

원본 로그: [04-swap-headroom-512-pf-swap-1.log](04-swap-headroom-512-pf-swap-1.log),
[04-swap-headroom-512-pf-swap-2.log](04-swap-headroom-512-pf-swap-2.log)

두 컨테이너 모두 **128MiB 상한을 확실히 넘어 183~191MiB에서 안정화**됐다
(새 상한 512MiB보다는 한참 낮은 값 — 무한정 커지는 게 아니라 이 워크로드의
실제 안정적인 swap 수요가 그 정도라는 뜻). `docker inspect` 결과 두
컨테이너 다 `OOMKilled=false`로 생존.

## 결론

**교수님 질문이 맞았다.** 원래 실험의 `swap=127.9MiB`는 워크로드의 진짜
수요가 아니라 `SWAP_HEADROOM_MB=128`이라는 인위적 상한에 막힌 값이었다.
실제 수요는 그보다 40~50% 더 컸다(183~191MiB). 상한을 풀어주자 그 실제
수요만큼 자연스럽게 안정화됐고, 128MiB로 막혀 있었을 때는 그 초과분이
swap으로 못 빠지고 `memory.current`로 쌓여 결국 OOM-kill로 이어진
것이었다 — 3차 실습에서 관찰한 blind spot 설명과 정확히 일치한다.

## 실험 후 원상복구

`SWAP_HEADROOM_MB`는 실험 직후 128로 되돌렸다(`git diff` 확인 결과 변경
없음 — 실험 전후 코드 동일). 이 실험은 일회성 검증용이며, 프로젝트의
기본값(128)을 바꾸는 결정이 아니다.
