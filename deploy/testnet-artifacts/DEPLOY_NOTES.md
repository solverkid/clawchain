# Testnet Deployment Notes

Chain ID: clawchain-testnet-1
Validators: 3
Genesis accounts: 1B uclaw each

## Before deploying to VPS:
1. Replace 'val1.example.com', 'val2.example.com', 'val3.example.com' 
   in persistent_peers.txt with actual VPS IPs
2. Copy each node's directory to the corresponding VPS
3. Set persistent_peers in config.toml on each node
4. Start with: clawchaind start --home ~/.clawchain

## Persistent Peers (replace IPs):
9d7e3a8ece5531497373e50b23ca22ca9cb19f8f@val1.example.com:26656,01d8c29dbf2d6b4895e35090f73eefd8269ba527@val2.example.com:26656,e9e545cef68400d72b97f80878c059989171c3da@val3.example.com:26656
