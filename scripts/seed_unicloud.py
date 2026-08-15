"""一键灌库脚本：自动登录管理员 → 把题库 manifest 灌进 uniCloud。

跳过手动配置：
  - 不需要你单独设 SM_ADMIN_TOKEN env
  - 不需要你先去 uniCloud 控制台开管理员

前提：
  1. 你的 uniCloud structmind-auth 云函数里已经设置了环境变量 SM_ADMIN_PASSWORD
     （控制台 → structmind-auth → 配置/环境变量）
  2. 题目 JSON 已经在 runtime/exports/manifest.json（运行过 export_question_bank.py）

使用：
  python scripts/seed_unicloud.py --password YOUR_ADMIN_PASSWORD
  python scripts/seed_unicloud.py                # 交互式输入密码

成功后：
  - 登录拿到 token（复用 ensureAdmin 流程）
  - 调用 structmind-import/importAll
  - 打印 import 结果（成功/跳过/校验错误）
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "runtime" / "exports"

DEFAULT_DOMAIN = "fc-mp-d74eb953-b479-43d3-9fda-e3524a6ad7e1.next.bspapp.com"
DEFAULT_FUNCTION = "structmind-auth"
IMPORT_FUNCTION = "structmind-import"
DEFAULT_ACCOUNT = "tanshuhong"


def call_function(domain: str, function_name: str, body: dict, timeout: int = 60) -> dict:
    """调用 uniCloud HTTP 接口（callFunction 协议）。"""
    url = f"https://{domain}/{function_name}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body_text}") from exc
    return json.loads(text)


def login(domain: str, account: str, password: str) -> str:
    """登录并返回 token；首次登录会自动通过 ensureAdmin 创建管理员账号。"""
    result = call_function(domain, DEFAULT_FUNCTION, {
        "action": "login", "params": {"account": account, "password": password},
    })
    if result.get("code") != 0:
        raise RuntimeError(f"登录失败: {result.get('message')}")
    return result["data"]["token"]


def import_all(domain: str, token: str, manifest: dict) -> dict:
    """灌库并返回 import 结果。"""
    result = call_function(domain, IMPORT_FUNCTION, {
        "action": "importAll",
        "params": {**manifest, "token": token},
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="一键登录管理员并灌库")
    parser.add_argument("--domain", default=os.environ.get(
        "SM_UNICLOUD_DOMAIN", DEFAULT_DOMAIN))
    parser.add_argument("--account", default=os.environ.get(
        "SM_ADMIN_ACCOUNT", DEFAULT_ACCOUNT))
    parser.add_argument("--password", help="管理员密码（不传则交互输入）")
    parser.add_argument("--manifest", default=str(EXPORT_DIR / "manifest.json"))
    parser.add_argument(
        "--import-fn",
        default=os.environ.get("SM_IMPORT_FUNCTION", IMPORT_FUNCTION),
        help="structmind-import 的函数名（默认 structmind-import）",
    )
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass(f"管理员密码（账号 {args.account}）: ")

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"未找到 {manifest_path}，请先运行：")
        print("  python scripts/export_question_bank.py")
        sys.exit(1)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = {
        "examQuestions": len(payload["examQuestions"]),
        "assignmentQuestions": len(payload["assignmentQuestions"]),
        "discussionQuestions": len(payload["discussionQuestions"]),
    }
    print(f"准备灌入: 考试 {counts['examQuestions']} / "
          f"作业 {counts['assignmentQuestions']} / "
          f"讨论 {counts['discussionQuestions']} 条")
    print(f"目标域名:  https://{args.domain}/{IMPORT_FUNCTION}")

    # Step 1: 登录（首次会自动 ensureAdmin 创建管理员）
    print("\n[1/2] 登录管理员...")
    token = login(args.domain, args.account, password)
    print(f"      ✓ 登录成功，token 长度 {len(token)}")

    # Step 2: 灌库
    print("\n[2/2] 灌库...")
    payload.pop("token", None)
    result = import_all(args.domain, token, payload)
    if result.get("code") != 0:
        raise RuntimeError(f"灌库失败: {result.get('message')}")

    data = result.get("data", {})
    summary = data.get("summary", {})
    details = data.get("details", {})
    print("      ✓ 完成")
    print(f"      总计: {summary.get('total_imported')} 条导入成功 / "
          f"{summary.get('total_skipped')} 条跳过")
    for label in ("exams", "assignments", "discussions"):
        d = details.get(label, {})
        errs = d.get("validationErrors") or []
        print(f"      {label:>14s}: {d.get('imported')}/{d.get('total')} 条"
              + (f" ({len(errs)} 个校验错误)" if errs else ""))
        for e in errs[:3]:
            print(f"        - 题目 {e.get('question_id', e.get('index'))}: {e.get('errors')}")
        if len(errs) > 3:
            print(f"        … 还有 {len(errs) - 3} 条")

    print("\n下一步：到浏览器练习页刷新，应能看到题目。")


if __name__ == "__main__":
    main()