#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TENCENT_FILE = (
    ROOT / "lepoker-gameserver" / "service" / "thrid_part" / "tencent_chat_room.go"
)
DEFAULT_BACKUP = ROOT / "build" / "poker-mtt" / "tencent_chat_room.go.orig"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply or restore local donor safety patches for poker-mtt harness runs.",
    )
    parser.add_argument("--tencent-file", type=Path, default=DEFAULT_TENCENT_FILE)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--restore", action="store_true")
    return parser.parse_args()


def ensure_backup(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(source, backup)


def patch_tencent_delete_group_member(source: str) -> tuple[str, bool]:
    guard = "\tif !config.ChatGroupAvailable {\n\t\treturn nil\n\t}\n"
    signature = "func DeleteGroupMember(ctx context.Context, groupID, chatRoomUserName string) (err error) {\n"
    start = source.find(signature)
    if start == -1:
        raise ValueError("DeleteGroupMember function not found")
    next_func = source.find("\nfunc ", start + len(signature))
    function_body = source[start:] if next_func == -1 else source[start:next_func]
    if "if !config.ChatGroupAvailable" in function_body:
        return source, False
    return source.replace(signature, signature + guard, 1), True


def restore_file(target: Path, backup: Path) -> int:
    if not backup.exists():
        print(f"backup file not found: {backup}", file=sys.stderr)
        return 1
    shutil.copy2(backup, target)
    print(f"restored {target} from {backup}")
    return 0


def main() -> int:
    args = parse_args()
    target = args.tencent_file.resolve()
    backup = args.backup.resolve()

    if args.restore:
        return restore_file(target, backup)
    if not target.exists():
        raise FileNotFoundError(f"tencent file not found: {target}")

    ensure_backup(target, backup)
    original = target.read_text(encoding="utf-8")
    patched, changed = patch_tencent_delete_group_member(original)
    if changed:
        target.write_text(patched, encoding="utf-8")
        print(f"patched {target}")
    else:
        print(f"already patched {target}")
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
