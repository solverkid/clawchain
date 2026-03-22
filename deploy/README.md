# ClawChain 3-Validator Testnet Deployment

## Node Roles

| Node | Role | Public Ports | Notes |
|------|------|-------------|-------|
| val1 | Validator + Sentry (RPC) | 26656, 26657, 9090 | Public RPC for miners |
| val2 | Validator | 26656 | P2P only |
| val3 | Validator | 26656 | P2P only |

## Machine Spec (minimum)

- **OS**: Ubuntu 22.04 LTS
- **CPU**: 2 vCPU
- **RAM**: 4 GB
- **Disk**: 40 GB SSD
- **Network**: 100 Mbps, static IP
- Cost: ~$10-20/mo per node (Hetzner/Vultr/DigitalOcean)

## Port Plan

| Port | Protocol | Purpose | Expose? |
|------|----------|---------|:-------:|
| 26656 | TCP | P2P | All nodes |
| 26657 | TCP | CometBFT RPC | val1 only |
| 9090 | TCP | gRPC | val1 only |
| 1317 | TCP | REST API | val1 only (optional) |

## Directory Structure (each node)

```
/opt/clawchain/
├── bin/
│   └── clawchaind
├── config/                 # symlink to ~/.clawchain/config
├── data/                   # symlink to ~/.clawchain/data
├── scripts/
│   ├── init-node.sh
│   ├── health-check.sh
│   └── height-check.sh
└── logs/
```

Chain home: `~/.clawchain` (default)
