# Repo Intel (GitHub scan)

## Thunderbolt / RDMA candidates
- https://github.com/Geramy/OdinLink-Five
  - RCCL plugin for Thunderbolt 5 + RDMA-like GPU communication
- https://github.com/ordishs/rdmamap-go
  - Go distributed map over Thunderbolt RDMA
- https://github.com/docdailey/thundercollective
  - 2-node collectives over Thunderbolt 5
- https://github.com/knoguchi/tb_rdma
  - Explicit RDMA-over-Thunderbolt experiment

## ANE ecosystem
- https://github.com/DeadByDawn101/ANE
  - Primary ANE reverse-engineered training path for cluster integration
- https://github.com/adamghaleb/apple-neural-engine
  - Alternate ANE training implementation reference

## Next actions
1. Pull code from tb_rdma + thundercollective patterns into TB4 transport design doc
2. Build adapter layer around ANE `train_large` / kernel scripts
3. Add benchmark harness comparing:
   - local Qwen-only
   - Qwen + ANE
   - Qwen + ANE + cloud fallback
