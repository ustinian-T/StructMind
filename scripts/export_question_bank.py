"""导出题库为 uniCloud structmind-import 云函数可直接消费的 JSON。

使用：
    python scripts/export_question_bank.py

输出：
    runtime/exports/exam_questions.json
    runtime/exports/assignment_questions.json
    runtime/exports/discussion_questions.json
    runtime/exports/manifest.json  —— 导入时直接 POST 给 structmind-import

字段映射与 uniCloud 校验保持一致（参考 uniCloud-aliyun/cloudfunctions/structmind-import/index.js）：
  考试题（type: single_choice | multi_choice | true_false | fill_blank）
  作业题（content + rubric + answer_source）
  讨论题（topic + content）
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.parser import (  # noqa: E402
    load_assignment_bank,
    load_question_bank,
)

EXPORT_DIR = ROOT / "runtime" / "exports"

# FastAPI 解析用中文题型 → uniCloud 英文题型
QTYPE_MAP = {
    "单选题": "single_choice",
    "多选题": "multi_choice",
    "判断题": "true_false",
    "填空题": "fill_blank",
}


def export_exam_questions() -> list[dict]:
    bank = load_question_bank()
    items: list[dict] = []
    for q in bank.questions:
        qtype = QTYPE_MAP.get(q.qtype)
        if qtype is None:
            print(f"[warn] 跳过未识别题型 q#{q.id} qtype={q.qtype!r}")
            continue
        # 选择题必须带 options（即使 raw 解析为空，AI 补全在生产里有；这里保持原样）
        options = q.options or []
        item: dict = {
            "question_id": f"EXAM_{q.id:04d}",
            "type": qtype,
            "chapter": q.chapter or "未分章",
            "content": q.stem,
            "answer": q.answer or "",
            "source_num": q.source_num or str(q.id),
            "source_order": q.source_order or q.id,
            "score": q.score or 1,
            "options": options,
            "images": q.images or [],
            "repaired": bool(q.repaired),
            "suspicious": q.suspicious or [],
            "stem_hash": q.stem_hash or "",
        }
        if qtype in ("single_choice", "multi_choice", "true_false"):
            # 选择题/判断题：options 是必须的（云函数 validateExamQuestion 会校验）
            if not options:
                print(f"[warn] 选择题缺选项 q#{q.id} type={qtype}")
        items.append(item)
    return items


def export_assignment_questions() -> list[dict]:
    bank = load_assignment_bank()
    items: list[dict] = []
    for q in bank.questions:
        item: dict = {
            "question_id": f"ASGN_{q.id:04d}",
            "type": "short_answer" if q.qtype == "简答题" else "fill_blank",
            "chapter": q.chapter or "未分章",
            "content": q.stem,
            "rubric": (q.answer or "").strip() or "（无评分标准）",
            "answer_source": getattr(q, "answer_source", "word_answer"),
            "source_num": q.source_num or str(q.id),
            "source_order": q.source_order or q.id,
            "images": q.images or [],
            "suspicious": q.suspicious or [],
            "stem_hash": q.stem_hash or "",
        }
        items.append(item)
    return items


def export_discussion_questions() -> list[dict]:
    bank = load_question_bank()
    items: list[dict] = []
    for d in bank.discussions:
        item: dict = {
            "question_id": f"DISC_{d.id:04d}",
            "chapter": d.chapter or "未分章",
            "topic": d.chapter or "讨论",
            "content": d.prompt,
            "source_order": d.source_order or d.id,
            "stem_hash": d.stem_hash or "",
        }
        items.append(item)
    return items


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    exams = export_exam_questions()
    assignments = export_assignment_questions()
    discussions = export_discussion_questions()

    (EXPORT_DIR / "exam_questions.json").write_text(
        json.dumps(exams, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (EXPORT_DIR / "assignment_questions.json").write_text(
        json.dumps(assignments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (EXPORT_DIR / "discussion_questions.json").write_text(
        json.dumps(discussions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # manifest 给 structmind-import/importAll 直接消费
    manifest = {
        "examQuestions": exams,
        "assignmentQuestions": assignments,
        "discussionQuestions": discussions,
    }
    (EXPORT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 60)
    print(f"导出目录: {EXPORT_DIR}")
    print(f"  考试题   {len(exams):>4} 道  类型分布: {dict(Counter(q['type'] for q in exams))}")
    print(f"  作业题   {len(assignments):>4} 道  类型分布: {dict(Counter(q['type'] for q in assignments))}")
    print(f"  讨论题   {len(discussions):>4} 道")
    print("=" * 60)
    print("下一步：")
    print("1) 通过 HBuilderX 控制台 → structmind-import → importAll 粘贴 manifest.json")
    print("   或者")
    print("2) 本地起 Python 服务后用 scripts/post_to_unicloud.py 自动 POST")


if __name__ == "__main__":
    main()