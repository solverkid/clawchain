#!/usr/bin/env bash
set -euo pipefail

ENDPOINT_URL="${POKER_MTT_DYNAMODB_ENDPOINT_URL:-http://127.0.0.1:38000}"
REGION="${AWS_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-local}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-local}"
export AWS_DEFAULT_REGION="$REGION"

require_aws_cli() {
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI is required to initialize DynamoDB Local tables" >&2
    echo "install with: python3 -m pip install awscli" >&2
    return 1
  fi
}

table_exists() {
  local table_name="$1"
  aws dynamodb describe-table \
    --endpoint-url "$ENDPOINT_URL" \
    --table-name "$table_name" >/dev/null 2>&1
}

create_poker_mtt_hands() {
  if table_exists poker_mtt_hands; then
    echo "DynamoDB Local table already exists: poker_mtt_hands"
    return 0
  fi
  aws dynamodb create-table \
    --endpoint-url "$ENDPOINT_URL" \
    --table-name poker_mtt_hands \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions \
      AttributeName=tournament_id,AttributeType=S \
      AttributeName=hand_id,AttributeType=S \
      AttributeName=room_id,AttributeType=S \
      AttributeName=completed_at,AttributeType=N \
    --key-schema \
      AttributeName=tournament_id,KeyType=HASH \
      AttributeName=hand_id,KeyType=RANGE \
    --global-secondary-indexes '[
      {
        "IndexName": "room_completed_at_idx",
        "KeySchema": [
          {"AttributeName": "room_id", "KeyType": "HASH"},
          {"AttributeName": "completed_at", "KeyType": "RANGE"}
        ],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]' >/dev/null
  echo "created DynamoDB Local table: poker_mtt_hands"
}

create_poker_mtt_user_hand_history() {
  if table_exists poker_mtt_user_hand_history; then
    echo "DynamoDB Local table already exists: poker_mtt_user_hand_history"
    return 0
  fi
  aws dynamodb create-table \
    --endpoint-url "$ENDPOINT_URL" \
    --table-name poker_mtt_user_hand_history \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions \
      AttributeName=player_user_id,AttributeType=S \
      AttributeName=completed_at_hand_id,AttributeType=S \
      AttributeName=tournament_id,AttributeType=S \
      AttributeName=hand_id,AttributeType=S \
    --key-schema \
      AttributeName=player_user_id,KeyType=HASH \
      AttributeName=completed_at_hand_id,KeyType=RANGE \
    --global-secondary-indexes '[
      {
        "IndexName": "tournament_hand_idx",
        "KeySchema": [
          {"AttributeName": "tournament_id", "KeyType": "HASH"},
          {"AttributeName": "hand_id", "KeyType": "RANGE"}
        ],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]' >/dev/null
  echo "created DynamoDB Local table: poker_mtt_user_hand_history"
}

require_aws_cli
create_poker_mtt_hands
create_poker_mtt_user_hand_history
