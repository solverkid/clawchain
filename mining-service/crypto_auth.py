"""
ClawChain Miner Identity — secp256k1 Signature Verification

Miners sign submissions with their private key. The server verifies
the signature against the miner's registered public key.

Signature scheme:
  message = SHA256(challenge_id + "|" + answer + "|" + miner_address + "|" + nonce)
  signature = secp256k1_sign(private_key, message)

Replay protection:
  - Nonce is a monotonically increasing integer per miner
  - Server rejects nonces <= last seen nonce for that miner
  - Nonce can be a Unix timestamp in milliseconds (recommended)
"""

import hashlib
import logging
import time

from eth_keys import keys as eth_keys

logger = logging.getLogger("clawchain.crypto_auth")


def build_sign_payload(challenge_id: str, answer: str, miner_address: str, nonce: int) -> bytes:
    """Build the canonical message bytes for signing.

    The message is: SHA256(challenge_id + "|" + answer + "|" + miner_address + "|" + str(nonce))
    Returns the 32-byte hash to be signed.
    """
    message = f"{challenge_id}|{answer}|{miner_address}|{nonce}"
    return hashlib.sha256(message.encode("utf-8")).digest()


def verify_signature(
    challenge_id: str,
    answer: str,
    miner_address: str,
    nonce: int,
    signature_hex: str,
    expected_pubkey_hex: str,
) -> tuple[bool, str]:
    """Verify a secp256k1 signature against the expected public key.

    Args:
        challenge_id: The challenge being answered
        answer: The miner's answer
        miner_address: The miner's registered address (claw1...)
        nonce: Monotonically increasing nonce (ms timestamp recommended)
        signature_hex: Hex-encoded 65-byte recoverable signature (0x prefix optional)
        expected_pubkey_hex: Hex-encoded 64-byte uncompressed public key (no 04 prefix)

    Returns:
        (valid: bool, error_message: str)
    """
    try:
        msg_hash = build_sign_payload(challenge_id, answer, miner_address, nonce)

        # Parse signature
        sig_hex = signature_hex.removeprefix("0x")
        sig_bytes = bytes.fromhex(sig_hex)

        if len(sig_bytes) != 65:
            return False, f"signature must be 65 bytes, got {len(sig_bytes)}"

        sig = eth_keys.Signature(sig_bytes)

        # Recover public key from signature
        recovered_pub = sig.recover_public_key_from_msg_hash(msg_hash)

        # Compare with expected public key
        expected_pub_hex = expected_pubkey_hex.removeprefix("0x")
        expected_pub = eth_keys.PublicKey(bytes.fromhex(expected_pub_hex))

        if recovered_pub != expected_pub:
            return False, "signature does not match registered public key"

        return True, ""

    except Exception as e:
        logger.warning(f"Signature verification error: {e}")
        return False, f"signature verification failed: {str(e)}"


def check_nonce(db, miner_address: str, nonce: int) -> tuple[bool, str]:
    """Check nonce for replay protection.

    Args:
        db: Database connection
        miner_address: The miner's address
        nonce: The submitted nonce

    Returns:
        (valid: bool, error_message: str)
    """
    row = db.execute(
        "SELECT last_nonce FROM miners WHERE address=?", (miner_address,)
    ).fetchone()

    if row is None:
        return False, "miner not found"

    last_nonce = row["last_nonce"] if row["last_nonce"] is not None else 0

    if nonce <= last_nonce:
        return False, f"nonce {nonce} is not greater than last nonce {last_nonce} (replay rejected)"

    # Check nonce is not too far in the future (max 5 minutes ahead)
    now_ms = int(time.time() * 1000)
    if nonce > now_ms + 300_000:
        return False, f"nonce too far in future (max 5 min ahead)"

    return True, ""


def update_nonce(db, miner_address: str, nonce: int):
    """Update the last seen nonce for a miner."""
    db.execute(
        "UPDATE miners SET last_nonce=? WHERE address=?",
        (nonce, miner_address),
    )
    db.commit()
