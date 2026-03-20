#!/usr/bin/env bash
# 启动 Cloudflare quick tunnel 并自动更新 Skill config 里的 RPC URL

SKILL_CONFIG="$HOME/.openclaw/workspace/skills/clawchain-miner/scripts/config.json"
REPO_CONFIG="/Users/orbot/.openclaw/workspace/projects/clawchain/skill/scripts/config.json"
LOG="/tmp/clawchain-tunnel.log"

# 杀掉旧 tunnel
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 2

# 启动 quick tunnel（后台）
cloudflared tunnel --url http://localhost:1317 > "$LOG" 2>&1 &
TUNNEL_PID=$!
echo "Tunnel PID: $TUNNEL_PID"

# 等 URL 出来（最多 30 秒）
for i in $(seq 1 30); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1)
  if [ -n "$URL" ]; then
    echo "✅ Tunnel URL: $URL"
    
    # 更新 Skill config
    if [ -f "$SKILL_CONFIG" ]; then
      python3 -c "
import json
with open('$SKILL_CONFIG') as f: c = json.load(f)
c['rpc_url'] = '$URL'
with open('$SKILL_CONFIG', 'w') as f: json.dump(c, f, indent=2)
print('Updated: $SKILL_CONFIG')
"
    fi
    
    if [ -f "$REPO_CONFIG" ]; then
      python3 -c "
import json
with open('$REPO_CONFIG') as f: c = json.load(f)
c['rpc_url'] = '$URL'
with open('$REPO_CONFIG', 'w') as f: json.dump(c, f, indent=2)
print('Updated: $REPO_CONFIG')
"
    fi
    
    # 保存 URL 到文件供其他脚本读取
    echo "$URL" > /tmp/clawchain-tunnel-url.txt
    exit 0
  fi
  sleep 1
done

echo "❌ Tunnel URL 未获取到"
exit 1
