"""把导出的题库 POST 到 uniCloud structmind-import 云函数。

需要在 uniCloud 控制台拿到云函数 URL（通常是
https://fc-mp-xxxx.bspapp.com/structmind-import），以及一个
管理员 token。

环境变量：
    SM_UNICLOUD_IMPORT_URL   —— 云函数完整 URL
    SM_ADMIN_TOKEN            —— structmind-import 的 requireAdmin 校验 token
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "runtime" / "exports"


def post_manifest(url: str, token: str, payload: dict) -> dict:
    body = json.dumps(
        {"action": "importAll", "params": {**payload, "token": token}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    url = os.environ.get("SM_UNICLOUD_IMPORT_URL", "").strip()
    token = os.environ.get("SM_ADMIN_TOKEN", "").strip()
    if not url or not token:
        print("缺少环境变量:")
        print("  SM_UNICLOUD_IMPORT_URL  (云函数 URL)")
        print("  SM_ADMIN_TOKEN            (管理员 token)")
        print()
        print("或者直接打开 HBuilderX → structmind-import → importAll,")
        print("把 runtime/exports/manifest.json 粘贴进去即可。")
        sys.exit(1)

    manifest_path = EXPORT_DIR / "manifest.json"
    if not manifest_path.exists():
        print(f"未找到 {manifest_path}，请先运行:")
        print("  python scripts/export_question_bank.py")
        sys.exit(1)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("token", None)

    print(f"POST {url}  共 {len(payload['examQuestions'])} 考试题 / "
          f"{len(payload['assignmentQuestions'])} 作业题 / "
          f"{len(payload['discussionQuestions'])} 讨论题 ...")
    result = post_manifest(url, token, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()