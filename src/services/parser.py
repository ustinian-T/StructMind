"""题库解析服务 —— DOCX 解析、题目加载、审计构建。"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from src.config import (
    ROOT,
    DOCX_PATH,
    ASSIGNMENT_DOCX_PATH,
    ASSET_DIR,
    FILL_REPAIRS,
    ASSIGNMENT_AI_REFERENCES,
)
from src.models.questions import ObjectiveQuestion, DiscussionQuestion, AssignmentQuestion
from src.models.banks import QuestionBank, AssignmentBank
from src.db.database import (
    text_hash,
    markers_match,
    normalize_space,
    normalize_fill,
    public_question,
    option_supplement_for,
)

QUESTION_RE = re.compile(r"(\d+)\.\s*\[(单选题|多选题|填空题|判断题)\]")
DISCUSSION_RE = re.compile(r"第[一二三四五六七八九十0-9]+章讨论")
ASSIGNMENT_QUESTION_RE = re.compile(r"(?:^|\n)(\d+)\.\s*\(([^)]+题)\)")
ASSIGNMENT_SECTION_RE = re.compile(r"(?:^|\n)([一二三四五六七八九十]+[.．、]\s*[^\n]*题[^\n]*)")
OPTION_RE = re.compile(r"^([A-H])\.\s*(.*)$")
IMAGE_RE = re.compile(r"\[IMAGE:([^\]]+)\]")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def docx_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_docx_stream(path: Path, bank_id: str = "exam") -> tuple[str, list[dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(f"题库文件不存在: {path}")

    asset_dir = ASSET_DIR / bank_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    paragraphs: list[str] = []
    image_exports: list[dict[str, Any]] = []

    with zipfile.ZipFile(path) as archive:
        rels_xml = archive.read("word/_rels/document.xml.rels")
        rels_root = ET.fromstring(rels_xml)
        rels: dict[str, str] = {}
        for rel in rels_root:
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rel_id and target:
                rels[rel_id] = target

        document_root = ET.fromstring(archive.read("word/document.xml"))
        paragraph_index = 0
        for para in document_root.iter():
            if local_name(para.tag) != "p":
                continue

            pieces: list[str] = []
            images: list[str] = []
            for node in para.iter():
                name = local_name(node.tag)
                if name == "t" and node.text:
                    pieces.append(node.text)
                elif name in {"tab", "br", "cr"}:
                    pieces.append("\n")
                for attr_name, attr_value in node.attrib.items():
                    if local_name(attr_name) == "embed" and attr_value in rels:
                        target = rels[attr_value]
                        if target.startswith("../"):
                            continue
                        zip_name = f"word/{target}"
                        if zip_name not in archive.namelist():
                            continue
                        filename = Path(target).name
                        out_path = asset_dir / filename
                        data = archive.read(zip_name)
                        if not out_path.exists() or out_path.read_bytes() != data:
                            out_path.write_bytes(data)
                        url = f"/assets/{bank_id}/{filename}"
                        images.append(url)
                        image_exports.append({
                            "paragraph": paragraph_index,
                            "target": target,
                            "url": url,
                            "bytes": len(data),
                        })

            text = "".join(pieces).replace(" ", " ").strip()
            if text:
                paragraphs.append(text)
            for url in images:
                paragraphs.append(f"[IMAGE:{url}]")
            paragraph_index += 1

    return "\n".join(paragraphs), image_exports


def make_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for match in QUESTION_RE.finditer(raw):
        events.append({
            "kind": "objective",
            "idx": match.start(),
            "text": match.group(0),
            "source_num": match.group(1),
            "qtype": match.group(2),
        })
    for match in DISCUSSION_RE.finditer(raw):
        events.append({"kind": "discussion", "idx": match.start(), "text": match.group(0)})
    events.sort(key=lambda item: item["idx"])
    return events


def clean_correct_answer(correct: str) -> str:
    correct = IMAGE_RE.sub("", correct)
    correct = re.sub(r"\n\s*AI讲解\s*$", "", correct).strip()
    return correct


def extract_score(segment: str) -> int | None:
    match = re.search(r"\n\s*(\d+)积分\b", segment)
    return int(match.group(1)) if match else None


def repair_fill_answer(stem: str, correct: str) -> tuple[str, bool]:
    for rule in FILL_REPAIRS:
        if rule["contains"] in stem:
            repaired_answer = f"(1) {rule['answer']}"
            if normalize_fill(correct) in {"", normalize_fill(repaired_answer)}:
                return correct if normalize_fill(correct) else repaired_answer, True
    if normalize_fill(correct) != "":
        return correct, False
    return correct, False


def suspicious_notes(
    qtype: str, stem: str, options: list[dict[str, str]], answer: str, repaired: bool,
) -> list[str]:
    notes: list[str] = []
    if not stem:
        notes.append("题干为空")
    if qtype in {"单选题", "多选题", "判断题"} and not options:
        notes.append("缺少选项")
    for option in options:
        if not option["text"]:
            notes.append(f"选项{option['key']}为空")
        if option["text"].strip() in {"O()", "o()"}:
            notes.append(f"选项{option['key']}疑似公式缺失")
    if qtype == "填空题" and normalize_fill(answer) == "":
        notes.append("填空答案缺失")
    if repaired:
        notes.append("正确答案由修复/校验表确认")
    return notes


def parse_objective_segment(
    segment: str, event: dict[str, Any], chapter: str, next_id: int,
) -> ObjectiveQuestion:
    images = IMAGE_RE.findall(segment)
    segment_without_images = IMAGE_RE.sub("", segment)
    head = QUESTION_RE.match(segment_without_images)
    if not head:
        raise ValueError(f"无法解析题目标记: {segment[:80]}")

    source_num = head.group(1)
    qtype = head.group(2)
    body = segment_without_images[head.end():].strip()
    answer_idx = body.find("正确答案：")
    my_idx = body.find("我的答案：")
    before_my = body[:my_idx] if my_idx >= 0 else body[:answer_idx if answer_idx >= 0 else None]

    raw_correct = ""
    if answer_idx >= 0:
        correct_area = body[answer_idx + len("正确答案："):]
        end_match = re.search(r"\n\s*\d+积分\b|\n\s*AI讲解\b", correct_area)
        raw_correct = correct_area[:end_match.start()].strip() if end_match else correct_area.strip()
    raw_correct = clean_correct_answer(raw_correct)

    lines = [line.strip() for line in before_my.splitlines() if line.strip()]
    options: list[dict[str, str]] = []
    stem_lines: list[str] = []
    for line in lines:
        option_match = OPTION_RE.match(line)
        if option_match:
            options.append({"key": option_match.group(1), "text": option_match.group(2).strip()})
        else:
            stem_lines.append(line)

    stem = "\n".join(stem_lines).strip()
    if qtype == "判断题" and not options:
        options = [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}]
    answer, repaired = repair_fill_answer(stem, raw_correct) if qtype == "填空题" else (raw_correct, False)
    suspicious = suspicious_notes(qtype, stem, options, answer, repaired)
    return ObjectiveQuestion(
        id=next_id, source_order=next_id, source_num=source_num, qtype=qtype,
        chapter=chapter or "未分章", stem=stem, options=options, answer=answer,
        raw_correct=raw_correct, score=extract_score(segment_without_images),
        images=images, repaired=repaired, suspicious=suspicious, stem_hash=text_hash(stem),
    )


def parse_discussion_segment(segment: str, source_order: int) -> DiscussionQuestion | None:
    marker_match = DISCUSSION_RE.match(segment)
    if not marker_match:
        return None
    chapter_match = re.match(r"(第[一二三四五六七八九十0-9]+章)讨论", marker_match.group(0))
    chapter = chapter_match.group(1) if chapter_match else "未分章"
    prompt = normalize_space(segment[marker_match.end():])
    if not prompt:
        return None
    return DiscussionQuestion(
        id=source_order, source_order=source_order, chapter=chapter,
        prompt=prompt, stem_hash=text_hash(prompt),
    )


def load_question_bank() -> QuestionBank:
    raw, image_exports = extract_docx_stream(DOCX_PATH, "exam")
    events = make_events(raw)
    questions: list[ObjectiveQuestion] = []
    discussions: list[DiscussionQuestion] = []
    current_chapter = ""
    next_discussion_id = 1

    for index, event in enumerate(events):
        next_idx = events[index + 1]["idx"] if index + 1 < len(events) else len(raw)
        segment = raw[event["idx"]:next_idx].strip()
        if event["kind"] == "discussion":
            chapter_match = re.match(r"(第[一二三四五六七八九十0-9]+章)讨论", event["text"])
            if chapter_match:
                current_chapter = chapter_match.group(1)
            discussion = parse_discussion_segment(segment, next_discussion_id)
            if discussion:
                discussions.append(discussion)
                next_discussion_id += 1
        elif event["kind"] == "objective":
            questions.append(parse_objective_segment(segment, event, current_chapter, len(questions) + 1))

    audit = build_audit(questions, discussions, image_exports)
    return QuestionBank(
        bank_id="exam", label="期末考试题库", docx_path=str(DOCX_PATH),
        docx_sha256=docx_sha256(DOCX_PATH), questions=questions,
        discussions=discussions, audit=audit,
    )


def build_audit(
    questions: list[ObjectiveQuestion],
    discussions: list[DiscussionQuestion],
    image_exports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    for question in questions:
        type_counts[question.qtype] = type_counts.get(question.qtype, 0) + 1
        for note in question.suspicious:
            supplemented = bool(option_supplement_for(question)) and ("选项" in note or "缺少选项" in note)
            audit.append({
                "kind": "objective",
                "question_id": question.id,
                "chapter": question.chapter,
                "qtype": question.qtype,
                "issue": note,
                "handling": "AI补全显示，标准答案不变" if supplemented
                else "保留练习" if "疑似" in note or "为空" in note
                else "修复后纳入",
            })
        if option_supplement_for(question):
            audit.append({
                "kind": "supplement",
                "question_id": question.id,
                "chapter": question.chapter,
                "qtype": question.qtype,
                "issue": "选项文本由补全表修复显示",
                "handling": "AI补全显示，标准答案不变",
            })

    expected = {"单选题": 218, "填空题": 68, "多选题": 12, "判断题": 25}
    for qtype, expected_count in expected.items():
        actual = type_counts.get(qtype, 0)
        if actual != expected_count:
            audit.append({
                "kind": "count", "question_id": None, "chapter": "", "qtype": qtype,
                "issue": f"题型数量为 {actual}, 预期 {expected_count}",
                "handling": "需要检查题库解析",
            })
    if len(questions) != 323:
        audit.append({
            "kind": "count", "question_id": None, "chapter": "", "qtype": "客观题",
            "issue": f"客观题数量为 {len(questions)}, 预期 323",
            "handling": "需要检查题库解析",
        })
    if len(discussions) != 35:
        audit.append({
            "kind": "count", "question_id": None, "chapter": "", "qtype": "讨论题",
            "issue": f"讨论题数量为 {len(discussions)}, 预期 35",
            "handling": "需要检查题库解析",
        })
    if len(image_exports) != 3:
        audit.append({
            "kind": "image", "question_id": None, "chapter": "", "qtype": "图片",
            "issue": f"题图数量为 {len(image_exports)}, 预期 3",
            "handling": "需要检查题图导出",
        })
    return audit


# ── 作业题库 ──


def assignment_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for match in ASSIGNMENT_SECTION_RE.finditer(raw):
        events.append({"kind": "section", "idx": match.start(), "text": match.group(1).strip()})
    for match in ASSIGNMENT_QUESTION_RE.finditer(raw):
        marker_start = match.start() + (1 if match.group(0).startswith("\n") else 0)
        events.append({
            "kind": "assignment", "idx": marker_start,
            "source_num": match.group(1), "qtype": match.group(2),
        })
    events.sort(key=lambda item: item["idx"])
    return events


def clean_assignment_stem(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^（\s*\d+(?:\.\d+)?分\s*）\s*", "", text)
    text = re.sub(r"^\(\s*\d+(?:\.\d+)?分\s*\)\s*", "", text)
    return text.strip()


def extract_assignment_answer(body: str) -> str:
    answer_idx = body.find("正确答案：")
    if answer_idx < 0:
        return ""
    correct_area = body[answer_idx + len("正确答案："):]
    correct_area = correct_area.split("AI讲解", 1)[0]
    lines: list[str] = []
    for line in correct_area.splitlines():
        stripped = line.strip()
        if re.match(r"^\*{3}：", stripped):
            break
        if re.match(r"^[一二三四五六七八九十]+[.．、]\s*.+题", stripped):
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def assignment_reference_for(stem: str) -> str:
    for item in ASSIGNMENT_AI_REFERENCES:
        if markers_match(stem, item["contains"]):
            return item["answer"]
    return ""


def parse_assignment_segment(
    segment: str, event: dict[str, Any], chapter: str, next_id: int,
) -> AssignmentQuestion:
    images = IMAGE_RE.findall(segment)
    segment_without_images = IMAGE_RE.sub("", segment).strip()
    head = re.match(r"(\d+)\.\s*\(([^)]+题)\)", segment_without_images)
    if not head:
        raise ValueError(f"无法解析作业题目标记: {segment[:80]}")

    source_num = head.group(1)
    qtype = head.group(2)
    body = segment_without_images[head.end():].strip()
    my_idx = body.find("我的答案：")
    answer_idx = body.find("正确答案：")
    stem_area = body[:my_idx if my_idx >= 0 else answer_idx if answer_idx >= 0 else None]
    lines = [line.rstrip() for line in stem_area.splitlines() if line.strip()]
    options: list[dict[str, str]] = []
    stem_lines: list[str] = []
    for line in lines:
        option_match = OPTION_RE.match(line.strip())
        if option_match:
            options.append({"key": option_match.group(1), "text": option_match.group(2).strip()})
        else:
            stem_lines.append(line)

    stem = clean_assignment_stem("\n".join(stem_lines))
    raw_correct = extract_assignment_answer(body)
    answer_source = "word_answer" if raw_correct else "none"
    answer = raw_correct
    suspicious: list[str] = []
    if not answer:
        reference = assignment_reference_for(stem)
        if reference:
            answer = reference
            answer_source = "ai_reference"
            suspicious.append("正确答案为空，已使用AI参考答案")
        else:
            suspicious.append("正确答案为空")
    if not stem:
        suspicious.append("题干为空")

    return AssignmentQuestion(
        id=next_id, source_order=next_id, source_num=source_num, qtype=qtype,
        chapter=chapter or "作业题库", stem=stem, options=options, answer=answer,
        answer_source=answer_source, raw_correct=raw_correct, images=images,
        suspicious=suspicious, stem_hash=text_hash(stem),
    )


def build_assignment_audit(
    questions: list[AssignmentQuestion], image_exports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    for question in questions:
        type_counts[question.qtype] = type_counts.get(question.qtype, 0) + 1
        for note in question.suspicious:
            audit.append({
                "kind": "assignment", "question_id": question.id,
                "chapter": question.chapter, "qtype": question.qtype,
                "issue": note,
                "handling": "AI参考答案" if question.answer_source == "ai_reference" else "保留题目",
            })

    expected = {"简答题": 25, "填空题": 1}
    for qtype, expected_count in expected.items():
        actual = type_counts.get(qtype, 0)
        if actual != expected_count:
            audit.append({
                "kind": "assignment_count", "question_id": None, "chapter": "",
                "qtype": qtype,
                "issue": f"题型数量为 {actual}, 预期 {expected_count}",
                "handling": "需要检查作业题库解析",
            })
    if len(questions) != 26:
        audit.append({
            "kind": "assignment_count", "question_id": None, "chapter": "",
            "qtype": "作业题",
            "issue": f"作业题数量为 {len(questions)}, 预期 26",
            "handling": "需要检查作业题库解析",
        })
    if len(image_exports) != 2:
        audit.append({
            "kind": "assignment_image", "question_id": None, "chapter": "",
            "qtype": "图片",
            "issue": f"作业题图数量为 {len(image_exports)}, 预期 2",
            "handling": "需要检查题图导出",
        })
    return audit


def load_assignment_bank() -> AssignmentBank:
    raw, image_exports = extract_docx_stream(ASSIGNMENT_DOCX_PATH, "assignment")
    events = assignment_events(raw)
    questions: list[AssignmentQuestion] = []
    current_chapter = "作业题库"
    for index, event in enumerate(events):
        next_idx = events[index + 1]["idx"] if index + 1 < len(events) else len(raw)
        if event["kind"] == "section":
            current_chapter = normalize_space(event["text"])
            continue
        segment = raw[event["idx"]:next_idx].strip()
        questions.append(parse_assignment_segment(segment, event, current_chapter, len(questions) + 1))

    audit = build_assignment_audit(questions, image_exports)
    return AssignmentBank(
        bank_id="assignment", label="期末考试作业题库",
        docx_path=str(ASSIGNMENT_DOCX_PATH),
        docx_sha256=docx_sha256(ASSIGNMENT_DOCX_PATH),
        questions=questions, audit=audit,
    )


def exam_bank_stats(bank: QuestionBank, db) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    chapters: dict[str, int] = {}
    repaired = 0
    suspicious = 0
    image_questions = 0
    for question in bank.questions:
        type_counts[question.qtype] = type_counts.get(question.qtype, 0) + 1
        chapters[question.chapter] = chapters.get(question.chapter, 0) + 1
        repaired += 1 if question.repaired else 0
        suspicious += 1 if any("疑似" in note or "为空" in note for note in question.suspicious) else 0
        image_questions += 1 if question.images else 0
    missing_answers = [question.id for question in bank.questions if not normalize_fill(question.answer)]
    incomplete_option_ids = []
    for question in bank.questions:
        public_options = public_question(question)["options"]
        if question.qtype in {"单选题", "多选题", "判断题"} and any(
            not option.get("text", "").strip() or option.get("text", "").strip() in {"O()", "o()"}
            for option in public_options
        ):
            incomplete_option_ids.append(question.id)
    integrity = {
        "objective_count_ok": len(bank.questions) == 323,
        "discussion_count_ok": len(bank.discussions) == 35,
        "type_counts_ok": type_counts == {"单选题": 218, "填空题": 68, "多选题": 12, "判断题": 25},
        "all_answers_present": not missing_answers,
        "missing_answer_ids": missing_answers,
        "all_display_options_present": not incomplete_option_ids,
        "incomplete_option_ids": incomplete_option_ids,
        "source_order_ok": [question.id for question in bank.questions] == list(range(1, len(bank.questions) + 1)),
        "image_question_ok": image_questions == 3,
    }
    return {
        "bank_id": bank.bank_id, "label": bank.label,
        "docx": {"path": bank.docx_path, "sha256": bank.docx_sha256},
        "counts": {
            "objective": len(bank.questions), "discussion": len(bank.discussions),
            "image_questions": image_questions, "repaired_answers": repaired,
            "suspicious_questions": suspicious,
            "ai_completed_questions": sum(1 for question in bank.questions if option_supplement_for(question)),
        },
        "type_counts": type_counts, "chapters": chapters,
        "audit": bank.audit, "integrity": integrity,
        "practice": db.summary("exam"),
    }


def assignment_bank_stats(bank: AssignmentBank, db) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    chapters: dict[str, int] = {}
    image_questions = 0
    word_answers = 0
    ai_references = 0
    missing_answers = []
    contaminated_ids = []
    for question in bank.questions:
        type_counts[question.qtype] = type_counts.get(question.qtype, 0) + 1
        chapters[question.chapter] = chapters.get(question.chapter, 0) + 1
        image_questions += 1 if question.images else 0
        word_answers += 1 if question.answer_source == "word_answer" else 0
        ai_references += 1 if question.answer_source == "ai_reference" else 0
        if not question.answer:
            missing_answers.append(question.id)
        combined = "\n".join([question.stem, question.answer])
        if "我的答案：" in combined or "***：" in combined:
            contaminated_ids.append(question.id)
    integrity = {
        "assignment_count_ok": len(bank.questions) == 26,
        "type_counts_ok": type_counts == {"简答题": 25, "填空题": 1},
        "word_answer_count_ok": word_answers == 23,
        "ai_reference_count_ok": ai_references == 3,
        "all_answers_present": not missing_answers,
        "missing_answer_ids": missing_answers,
        "no_my_answer_or_score_text": not contaminated_ids,
        "contaminated_ids": contaminated_ids,
        "source_order_ok": [question.id for question in bank.questions] == list(range(1, len(bank.questions) + 1)),
        "image_question_ok": image_questions == 2,
    }
    return {
        "bank_id": bank.bank_id, "label": bank.label,
        "docx": {"path": bank.docx_path, "sha256": bank.docx_sha256},
        "counts": {
            "questions": len(bank.questions), "image_questions": image_questions,
            "word_answers": word_answers, "ai_reference_answers": ai_references,
            "missing_answers": len(missing_answers),
        },
        "type_counts": type_counts, "chapters": chapters,
        "audit": bank.audit, "integrity": integrity,
        "practice": db.summary("assignment"),
    }


def stats_payload(exam_bank: QuestionBank, assignment_bank: AssignmentBank, db, config: dict) -> dict[str, Any]:
    exam = exam_bank_stats(exam_bank, db)
    assignment = assignment_bank_stats(assignment_bank, db)
    return {
        **exam,
        "banks": {"exam": exam, "assignment": assignment},
        "models": config["models"],
        "providers": config["providers"],
        "default_provider": config["default_provider"],
        "default_model": config["default_model"],
        "ai_configured": config["ai_configured"],
        "api_key_source": config["api_key_source"],
        "key_preview": config["key_preview"],
        "timeout_seconds": config["timeout_seconds"],
    }


def supplements_payload(exam_bank: QuestionBank, assignment_bank: AssignmentBank) -> dict[str, Any]:
    items = []
    seen_exam: set[int] = set()
    for question in exam_bank.questions:
        supplement = option_supplement_for(question)
        if not supplement or question.id in seen_exam:
            continue
        seen_exam.add(question.id)
        items.append({
            "bank_id": "exam", "kind": "option_supplement", "question_id": question.id,
            "chapter": question.chapter, "qtype": question.qtype,
            "stem": question.stem, "answer": question.answer,
            "options": supplement["options"], "note": supplement["note"],
        })
    for question in assignment_bank.questions:
        if question.answer_source != "ai_reference":
            continue
        items.append({
            "bank_id": "assignment", "kind": "ai_reference_answer",
            "question_id": question.id, "chapter": question.chapter,
            "qtype": question.qtype, "stem": question.stem,
            "answer": question.answer, "note": "Word 正确答案为空，使用 AI参考答案。",
        })
    return {"items": items, "count": len(items)}
