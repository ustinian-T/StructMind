from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import random
import re
import secrets
import socket
import sqlite3
import ssl
import time
import unicodedata
import uuid
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
DOCX_PATH = ROOT / "数据结构期末考试题库.docx"
MAX_SESSION_AGE = 86400 * 7  # 7天会话过期

def create_proxy_opener() -> request.OpenerDirector:
    proxies = {}
    for scheme, names in {
        "http": ("HTTP_PROXY", "http_proxy"),
        "https": ("HTTPS_PROXY", "https_proxy"),
    }.items():
        value = next((os.environ.get(name) for name in names if os.environ.get(name)), "")
        if value:
            proxies[scheme] = value
    proxy_handler = request.ProxyHandler(proxies)
    opener = request.build_opener(proxy_handler)
    return opener

DEEPSEEK_OPENER = create_proxy_opener()
ASSIGNMENT_DOCX_PATH = ROOT / "期末考试作业题库.docx"
STATIC_DIR = ROOT / "static"
RUNTIME_DIR = ROOT / "runtime"
ASSET_DIR = RUNTIME_DIR / "assets"
DB_PATH = RUNTIME_DIR / "practice.sqlite3"
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
AI_TIMEOUT_SECONDS = 120
AI_MAX_RETRIES = 0

AI_PROVIDERS = {
    "zhipu": {
        "label": "智谱AI",
        "url": ZHIPU_URL,
        "models": ["glm-5.1", "glm-5", "glm-4.7-flash"],
        "default_model": "glm-5.1",
        "env": ["BIGMODEL_API_KEY", "ZHIPU_API_KEY", "ZHIPUAI_API_KEY"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "url": DEEPSEEK_URL,
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-v4-flash",
        "env": ["DEEPSEEK_API_KEY"],
    },
}
ALLOWED_MODELS = {model for provider in AI_PROVIDERS.values() for model in provider["models"]}
MODEL_ALIASES = {"gml-4.7-flash": "glm-4.7-flash"}
RUNTIME_CONFIG = {
    "api_keys": {"zhipu": "", "deepseek": ""},
    "default_provider": "zhipu",
    "default_model": "glm-5.1",
}

QUESTION_RE = re.compile(r"(\d+)\.\s*\[(单选题|多选题|填空题|判断题)\]")
DISCUSSION_RE = re.compile(r"第[一二三四五六七八九十0-9]+章讨论")
ASSIGNMENT_QUESTION_RE = re.compile(r"(?:^|\n)(\d+)\.\s*\(([^)]+题)\)")
ASSIGNMENT_SECTION_RE = re.compile(r"(?:^|\n)([一二三四五六七八九十]+[.．、]\s*[^\n]*题[^\n]*)")
OPTION_RE = re.compile(r"^([A-H])\.\s*(.*)$")
IMAGE_RE = re.compile(r"\[IMAGE:([^\]]+)\]")

FILL_REPAIRS = [
    {"contains": "123按顺序进栈", "answer": "312"},
    {"contains": "按列存储时元素A36", "answer": "1192"},
    {"contains": "该树中叶子结点的个数", "answer": "8"},
    {"contains": "拥有100个结点的完全二叉树的最大层数", "answer": "7"},
    {"contains": "入度之和是所有顶点出度之和的____倍", "answer": "1"},
]

AI_OPTION_SUPPLEMENTS = {
    6: {
        "contains": ["执行下面的程序段的时间复杂度", "a[i][j]=i*j"],
        "note": "补全时间复杂度选项，标准答案仍为 C。",
        "options": {"A": "O(m)", "B": "O(n)", "C": "O(m*n)", "D": "O(m+n)"},
    },
    7: {
        "contains": ["执行下面程序段时", "语句S的执行次数"],
        "note": "补全语句频度选项，标准答案仍为 D。",
        "options": {"A": "n", "B": "n^2", "C": "n(n+1)", "D": "n(n+1)/2"},
    },
    14: {
        "contains": ["顺序表", "插入一个元素", "移动表中"],
        "note": "补全顺序表平均移动次数干扰项，标准答案仍为 C。",
        "options": {"A": "n", "B": "n+1", "C": "n/2", "D": "(n-1)/2"},
    },
    117: {
        "contains": ["n行n列的带状矩阵", "非零元素的个数"],
        "note": "补全三对角带状矩阵非零元素个数选项，标准答案仍为 B。",
        "options": {"A": "3n", "B": "3n-2", "C": "3n+2", "D": "n^2"},
    },
    118: {
        "contains": ["上三角矩阵", "按列优先", "非零元素aij"],
        "note": "补全上三角矩阵列优先压缩地址公式，标准答案仍为 D。",
        "options": {
            "A": "i(i-1)/2+j-1",
            "B": "j(j+1)/2+i-1",
            "C": "j(j-1)/2+i",
            "D": "j(j-1)/2+i-1",
        },
    },
    151: {
        "contains": ["高度为h的完全二叉树", "至少有"],
        "note": "补全完全二叉树最少结点数选项，标准答案仍为 C。",
        "options": {"A": "2^h-1", "B": "2^(h-1)-1", "C": "2^(h-1)", "D": "2^h"},
    },
    158: {
        "contains": ["高度为k的满二叉树", "结点总数"],
        "note": "补全满二叉树结点总数公式选项，标准答案仍为 C。",
        "options": {"A": "2^(k-1)", "B": "2^(k-1)-1", "C": "2^k-1", "D": "2k"},
    },
    209: {
        "contains": ["n个顶点的无向图", "邻接矩阵表示", "矩阵的大小"],
        "note": "补全邻接矩阵规模选项，标准答案仍为 C。",
        "options": {"A": "n", "B": "n(n-1)", "C": "n^2", "D": "n(n-1)/2"},
    },
}

ASSIGNMENT_AI_REFERENCES = [
    {
        "contains": ["七个带权结点", "3,5,7,2,6,12,15", "哈夫曼树"],
        "answer": "按哈夫曼算法依次合并最小权值：2+3=5，5+5=10，6+7=13，10+12=22，13+15=28，22+28=50。带权路径长度 WPL 等于各次合并权值之和：5+10+13+22+28+50=128。",
    },
    {
        "contains": ["10个结点的折半判定树", "查找成功的平均查找长度"],
        "answer": "10 个结点的折半判定树按折半查找划分，层数分布为第 1 层 1 个结点、第 2 层 2 个结点、第 3 层 4 个结点、第 4 层 3 个结点。等概率查找成功的平均查找长度 ASL=(1*1+2*2+3*4+4*3)/10=29/10。",
    },
    {
        "contains": ["Hash(key)=key%7", "线性探测", "查找成功和不成功"],
        "answer": "散列地址依次为：36->1，13->6，40->5，63->0，22->1，6->6。采用线性探测后，哈希表 A[0..9] 为：[63,36,22,空,空,40,13,6,空,空]。查找成功比较次数为 1,1,1,1,2,2，ASL成功=8/6=4/3。查找不成功按地址 0..6 计算，比较次数为 4,3,2,1,1,4,3，ASL不成功=18/7。",
    },
]


@dataclass
class ObjectiveQuestion:
    id: int
    source_order: int
    source_num: str
    qtype: str
    chapter: str
    stem: str
    options: list[dict[str, str]]
    answer: str
    raw_correct: str
    score: int | None
    images: list[str] = field(default_factory=list)
    repaired: bool = False
    suspicious: list[str] = field(default_factory=list)
    stem_hash: str = ""


@dataclass
class DiscussionQuestion:
    id: int
    source_order: int
    chapter: str
    prompt: str
    stem_hash: str


@dataclass
class QuestionBank:
    bank_id: str
    label: str
    docx_path: str
    docx_sha256: str
    questions: list[ObjectiveQuestion]
    discussions: list[DiscussionQuestion]
    audit: list[dict[str, Any]]

    @property
    def by_id(self) -> dict[int, ObjectiveQuestion]:
        return {q.id: q for q in self.questions}

    @property
    def discussion_by_id(self) -> dict[int, DiscussionQuestion]:
        return {q.id: q for q in self.discussions}


@dataclass
class AssignmentQuestion:
    id: int
    source_order: int
    source_num: str
    qtype: str
    chapter: str
    stem: str
    options: list[dict[str, str]]
    answer: str
    answer_source: str
    raw_correct: str
    images: list[str] = field(default_factory=list)
    suspicious: list[str] = field(default_factory=list)
    stem_hash: str = ""


@dataclass
class AssignmentBank:
    bank_id: str
    label: str
    docx_path: str
    docx_sha256: str
    questions: list[AssignmentQuestion]
    audit: list[dict[str, Any]]

    @property
    def by_id(self) -> dict[int, AssignmentQuestion]:
        return {q.id: q for q in self.questions}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def normalize_hash_text(text: str) -> str:
    text = normalize_space(text).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[，。；：、,. ;:]", "", text)
    return text


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize_hash_text(text).encode("utf-8")).hexdigest()[:16]


def markers_match(text: str, markers: list[str]) -> bool:
    normalized = normalize_hash_text(text)
    return all(normalize_hash_text(marker) in normalized for marker in markers)


def option_needs_supplement(question: ObjectiveQuestion) -> bool:
    return any(
        not option.get("text", "").strip() or option.get("text", "").strip() in {"O()", "o()"}
        for option in question.options
    )


def option_supplement_for(question: ObjectiveQuestion) -> dict[str, Any] | None:
    for supplement in AI_OPTION_SUPPLEMENTS.values():
        markers = supplement.get("contains") or []
        if markers and option_needs_supplement(question) and markers_match(question.stem, markers):
            return supplement
    return AI_OPTION_SUPPLEMENTS.get(question.id)


def assignment_reference_for(stem: str) -> str:
    for item in ASSIGNMENT_AI_REFERENCES:
        if markers_match(stem, item["contains"]):
            return item["answer"]
    return ""


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
                        image_exports.append(
                            {
                                "paragraph": paragraph_index,
                                "target": target,
                                "url": url,
                                "bytes": len(data),
                            }
                        )

            text = "".join(pieces).replace("\u00a0", " ").strip()
            if text:
                paragraphs.append(text)
            for url in images:
                paragraphs.append(f"[IMAGE:{url}]")
            paragraph_index += 1

    return "\n".join(paragraphs), image_exports


def make_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for match in QUESTION_RE.finditer(raw):
        events.append(
            {
                "kind": "objective",
                "idx": match.start(),
                "text": match.group(0),
                "source_num": match.group(1),
                "qtype": match.group(2),
            }
        )
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


def parse_objective_segment(
    segment: str,
    event: dict[str, Any],
    chapter: str,
    next_id: int,
) -> ObjectiveQuestion:
    images = IMAGE_RE.findall(segment)
    segment_without_images = IMAGE_RE.sub("", segment)
    head = QUESTION_RE.match(segment_without_images)
    if not head:
        raise ValueError(f"无法解析题目标记: {segment[:80]}")

    source_num = head.group(1)
    qtype = head.group(2)
    body = segment_without_images[head.end() :].strip()
    answer_idx = body.find("正确答案：")
    my_idx = body.find("我的答案：")
    before_my = body[:my_idx] if my_idx >= 0 else body[:answer_idx if answer_idx >= 0 else None]

    raw_correct = ""
    if answer_idx >= 0:
        correct_area = body[answer_idx + len("正确答案：") :]
        end_match = re.search(r"\n\s*\d+积分\b|\n\s*AI讲解\b", correct_area)
        raw_correct = correct_area[: end_match.start()].strip() if end_match else correct_area.strip()
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
        id=next_id,
        source_order=next_id,
        source_num=source_num,
        qtype=qtype,
        chapter=chapter or "未分章",
        stem=stem,
        options=options,
        answer=answer,
        raw_correct=raw_correct,
        score=extract_score(segment_without_images),
        images=images,
        repaired=repaired,
        suspicious=suspicious,
        stem_hash=text_hash(stem),
    )


def parse_discussion_segment(segment: str, source_order: int) -> DiscussionQuestion | None:
    marker_match = DISCUSSION_RE.match(segment)
    if not marker_match:
        return None
    chapter_match = re.match(r"(第[一二三四五六七八九十0-9]+章)讨论", marker_match.group(0))
    chapter = chapter_match.group(1) if chapter_match else "未分章"
    prompt = normalize_space(segment[marker_match.end() :])
    if not prompt:
        return None
    return DiscussionQuestion(
        id=source_order,
        source_order=source_order,
        chapter=chapter,
        prompt=prompt,
        stem_hash=text_hash(prompt),
    )


def suspicious_notes(
    qtype: str,
    stem: str,
    options: list[dict[str, str]],
    answer: str,
    repaired: bool,
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


def load_question_bank() -> QuestionBank:
    raw, image_exports = extract_docx_stream(DOCX_PATH, "exam")
    events = make_events(raw)
    questions: list[ObjectiveQuestion] = []
    discussions: list[DiscussionQuestion] = []
    current_chapter = ""
    next_discussion_id = 1

    for index, event in enumerate(events):
        next_idx = events[index + 1]["idx"] if index + 1 < len(events) else len(raw)
        segment = raw[event["idx"] : next_idx].strip()
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
        bank_id="exam",
        label="期末考试题库",
        docx_path=str(DOCX_PATH),
        docx_sha256=docx_sha256(DOCX_PATH),
        questions=questions,
        discussions=discussions,
        audit=audit,
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
            audit.append(
                {
                    "kind": "objective",
                    "question_id": question.id,
                    "chapter": question.chapter,
                    "qtype": question.qtype,
                    "issue": note,
                    "handling": (
                        "AI补全显示，标准答案不变"
                        if supplemented
                        else "保留练习" if "疑似" in note or "为空" in note else "修复后纳入"
                    ),
                }
            )
        if option_supplement_for(question):
            audit.append(
                {
                    "kind": "supplement",
                    "question_id": question.id,
                    "chapter": question.chapter,
                    "qtype": question.qtype,
                    "issue": "选项文本由补全表修复显示",
                    "handling": "AI补全显示，标准答案不变",
                }
            )

    expected = {"单选题": 218, "填空题": 68, "多选题": 12, "判断题": 25}
    for qtype, expected_count in expected.items():
        actual = type_counts.get(qtype, 0)
        if actual != expected_count:
            audit.append(
                {
                    "kind": "count",
                    "question_id": None,
                    "chapter": "",
                    "qtype": qtype,
                    "issue": f"题型数量为 {actual}, 预期 {expected_count}",
                    "handling": "需要检查题库解析",
                }
            )
    if len(questions) != 323:
        audit.append(
            {
                "kind": "count",
                "question_id": None,
                "chapter": "",
                "qtype": "客观题",
                "issue": f"客观题数量为 {len(questions)}, 预期 323",
                "handling": "需要检查题库解析",
            }
        )
    if len(discussions) != 35:
        audit.append(
            {
                "kind": "count",
                "question_id": None,
                "chapter": "",
                "qtype": "讨论题",
                "issue": f"讨论题数量为 {len(discussions)}, 预期 35",
                "handling": "需要检查题库解析",
            }
        )
    if len(image_exports) != 3:
        audit.append(
            {
                "kind": "image",
                "question_id": None,
                "chapter": "",
                "qtype": "图片",
                "issue": f"题图数量为 {len(image_exports)}, 预期 3",
                "handling": "需要检查题图导出",
            }
        )
    return audit


def assignment_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for match in ASSIGNMENT_SECTION_RE.finditer(raw):
        events.append({"kind": "section", "idx": match.start(), "text": match.group(1).strip()})
    for match in ASSIGNMENT_QUESTION_RE.finditer(raw):
        marker_start = match.start() + (1 if match.group(0).startswith("\n") else 0)
        events.append(
            {
                "kind": "assignment",
                "idx": marker_start,
                "source_num": match.group(1),
                "qtype": match.group(2),
            }
        )
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
    correct_area = body[answer_idx + len("正确答案：") :]
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


def parse_assignment_segment(
    segment: str,
    event: dict[str, Any],
    chapter: str,
    next_id: int,
) -> AssignmentQuestion:
    images = IMAGE_RE.findall(segment)
    segment_without_images = IMAGE_RE.sub("", segment).strip()
    head = re.match(r"(\d+)\.\s*\(([^)]+题)\)", segment_without_images)
    if not head:
        raise ValueError(f"无法解析作业题目标记: {segment[:80]}")

    source_num = head.group(1)
    qtype = head.group(2)
    body = segment_without_images[head.end() :].strip()
    my_idx = body.find("我的答案：")
    answer_idx = body.find("正确答案：")
    stem_area = body[: my_idx if my_idx >= 0 else answer_idx if answer_idx >= 0 else None]
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
        id=next_id,
        source_order=next_id,
        source_num=source_num,
        qtype=qtype,
        chapter=chapter or "作业题库",
        stem=stem,
        options=options,
        answer=answer,
        answer_source=answer_source,
        raw_correct=raw_correct,
        images=images,
        suspicious=suspicious,
        stem_hash=text_hash(stem),
    )


def build_assignment_audit(
    questions: list[AssignmentQuestion],
    image_exports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    for question in questions:
        type_counts[question.qtype] = type_counts.get(question.qtype, 0) + 1
        for note in question.suspicious:
            audit.append(
                {
                    "kind": "assignment",
                    "question_id": question.id,
                    "chapter": question.chapter,
                    "qtype": question.qtype,
                    "issue": note,
                    "handling": "AI参考答案" if question.answer_source == "ai_reference" else "保留题目",
                }
            )

    expected = {"简答题": 25, "填空题": 1}
    for qtype, expected_count in expected.items():
        actual = type_counts.get(qtype, 0)
        if actual != expected_count:
            audit.append(
                {
                    "kind": "assignment_count",
                    "question_id": None,
                    "chapter": "",
                    "qtype": qtype,
                    "issue": f"题型数量为 {actual}, 预期 {expected_count}",
                    "handling": "需要检查作业题库解析",
                }
            )
    if len(questions) != 26:
        audit.append(
            {
                "kind": "assignment_count",
                "question_id": None,
                "chapter": "",
                "qtype": "作业题",
                "issue": f"作业题数量为 {len(questions)}, 预期 26",
                "handling": "需要检查作业题库解析",
            }
        )
    if len(image_exports) != 2:
        audit.append(
            {
                "kind": "assignment_image",
                "question_id": None,
                "chapter": "",
                "qtype": "图片",
                "issue": f"作业题图数量为 {len(image_exports)}, 预期 2",
                "handling": "需要检查题图导出",
            }
        )
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
        segment = raw[event["idx"] : next_idx].strip()
        questions.append(parse_assignment_segment(segment, event, current_chapter, len(questions) + 1))

    audit = build_assignment_audit(questions, image_exports)
    return AssignmentBank(
        bank_id="assignment",
        label="期末考试作业题库",
        docx_path=str(ASSIGNMENT_DOCX_PATH),
        docx_sha256=docx_sha256(ASSIGNMENT_DOCX_PATH),
        questions=questions,
        audit=audit,
    )


def normalize_choice_answer(answer: Any) -> str:
    if isinstance(answer, list):
        answer = "".join(str(item) for item in answer)
    answer = unicodedata.normalize("NFKC", str(answer or "")).strip()
    compact = re.sub(r"[\s\u00a0.。．,，:：;；、()（）\[\]【】]+", "", answer).upper()
    replacements = {
        "√": "A",
        "✓": "A",
        "✔": "A",
        "对": "A",
        "对的": "A",
        "是": "A",
        "是的": "A",
        "正确": "A",
        "正确的": "A",
        "YES": "A",
        "Y": "A",
        "TRUE": "A",
        "T": "A",
        "×": "B",
        "X": "B",
        "✕": "B",
        "✖": "B",
        "错": "B",
        "错的": "B",
        "否": "B",
        "不是": "B",
        "错误": "B",
        "错误的": "B",
        "不对": "B",
        "不正确": "B",
        "NO": "B",
        "N": "B",
        "FALSE": "B",
        "F": "B",
    }
    if compact in replacements:
        return replacements[compact]
    if any(marker in compact for marker in ("错误", "不正确", "不对", "错")):
        return "B"
    if any(marker in compact for marker in ("正确", "对", "√", "✓", "✔")):
        return "A"
    return re.sub(r"[^A-H]", "", compact)


def normalize_multi_answer(answer: Any) -> str:
    return "".join(sorted(set(normalize_choice_answer(answer))))


def normalize_fill(text: Any) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = re.sub(r"\(\s*\d+\s*\)", "", value)
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",").replace("；", ";").replace("：", ":")
    value = value.replace("×", "*").replace("＊", "*")
    value = re.sub(r"\s+", "", value)
    value = value.replace("＝", "=").replace("==", "=")
    return value.lower()


def fill_candidates(answer: str) -> list[str]:
    answer = answer.strip()
    parts = re.findall(r"\(\s*\d+\s*\)\s*([^\n]+)", answer)
    text = " ".join(parts) if parts else answer
    candidates = re.split(r"\s*(?:或|/|、)\s*", text)
    normalized = [normalize_fill(item) for item in candidates if normalize_fill(item)]
    return normalized or [normalize_fill(answer)]


def grade_answer(question: ObjectiveQuestion, user_answer: Any) -> dict[str, Any]:
    if question.qtype == "多选题":
        user_norm = normalize_multi_answer(user_answer)
        correct_norm = normalize_multi_answer(question.answer)
        is_correct = user_norm == correct_norm
    elif question.qtype == "判断题":
        user_norm = normalize_choice_answer(user_answer)
        correct_norm = normalize_choice_answer(question.answer)
        is_correct = bool(user_norm) and user_norm == correct_norm
    elif question.qtype == "单选题" and re.search(r"[A-H]", normalize_choice_answer(question.answer)):
        user_norm = normalize_choice_answer(user_answer)
        correct_norm = normalize_choice_answer(question.answer)
        is_correct = user_norm == correct_norm
    elif question.qtype == "填空题":
        user_norm = normalize_fill(user_answer)
        candidates = fill_candidates(question.answer)
        correct_norm = " / ".join(candidates)
        is_correct = user_norm in candidates
    else:
        user_norm = normalize_fill(user_answer)
        correct_norm = normalize_fill(question.answer)
        is_correct = user_norm == correct_norm

    return {
        "is_correct": is_correct,
        "user_normalized": user_norm,
        "correct_normalized": correct_norm,
        "correct_answer": question.answer,
        "analysis": objective_analysis(question, is_correct),
    }


def objective_analysis(question: ObjectiveQuestion, is_correct: bool) -> str:
    if getattr(question, "repaired", False):
        repair_note = "本题列入答案修复/校验表，已按题干确认标准答案。"
    else:
        repair_note = ""
    if is_correct:
        return f"答案正确。{repair_note}".strip()
    if question.qtype == "填空题":
        return f"答案不匹配。填空题已忽略空格、编号和常见符号差异。{repair_note}".strip()
    if question.qtype == "多选题":
        return "答案不匹配。多选题按选项集合比较，顺序不影响结果。"
    return f"答案不匹配，标准答案为 {question.answer}。{repair_note}".strip()


class PracticeDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    qtype TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS ai_questions (
                    id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    source_question_id INTEGER NOT NULL,
                    qtype TEXT NOT NULL,
                    stem TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    analysis TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS discussion_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discussion_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS assignment_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    answer_source TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    role TEXT DEFAULT 'student',
                    status TEXT DEFAULT 'pending',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS user_profile (
                    user_id INTEGER PRIMARY KEY,
                    chapter_accuracy_json TEXT DEFAULT '{}',
                    type_accuracy_json TEXT DEFAULT '{}',
                    weak_concepts_json TEXT DEFAULT '[]',
                    strong_concepts_json TEXT DEFAULT '[]',
                    total_attempts INTEGER DEFAULT 0,
                    total_correct INTEGER DEFAULT 0,
                    practice_streak INTEGER DEFAULT 0,
                    last_practice_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER,
                    mode TEXT DEFAULT 'tutor',
                    messages_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS generated_questions (
                    stem_hash TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    account TEXT NOT NULL,
                    ip TEXT,
                    success INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS custom_banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    questions_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    FOREIGN KEY (owner_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS learning_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_data_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS community_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER,
                    bank_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS community_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES community_posts(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                """
            )
            # 迁移：为旧表添加 user_id 列（如果不存在）
            _allowed_tables = {"attempts", "ai_questions", "discussion_feedback", "assignment_feedback"}
            for table in _allowed_tables:
                if table not in _allowed_tables:
                    continue  # 安全防护：仅允许预定义表名
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass

    def record_attempt(
        self,
        question_id: int,
        source: str,
        qtype: str,
        user_answer: Any,
        correct_answer: str,
        is_correct: bool,
        user_id: int = 0,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO attempts
                    (question_id, source, qtype, user_answer, correct_answer, is_correct, created_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    source,
                    qtype,
                    json.dumps(user_answer, ensure_ascii=False),
                    correct_answer,
                    1 if is_correct else 0,
                    time.time(),
                    user_id,
                ),
            )

    def record_ai_question(
        self,
        item: dict[str, Any],
        model: str,
        source_question_id: int,
    ) -> str:
        ai_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO ai_questions
                    (id, model, source_question_id, qtype, stem, options_json, answer, analysis, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ai_id,
                    model,
                    source_question_id,
                    item["qtype"],
                    item["stem"],
                    json.dumps(item.get("options", []), ensure_ascii=False),
                    item["answer"],
                    item.get("analysis", ""),
                    time.time(),
                ),
            )
        return ai_id

    def get_ai_question(self, ai_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM ai_questions WHERE id = ?", (ai_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "model": row["model"],
            "source_question_id": row["source_question_id"],
            "qtype": row["qtype"],
            "stem": row["stem"],
            "options": json.loads(row["options_json"]),
            "answer": row["answer"],
            "analysis": row["analysis"],
            "created_at": row["created_at"],
        }

    def record_discussion_feedback(
        self,
        discussion_id: int,
        model: str,
        user_answer: str,
        feedback: dict[str, Any],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO discussion_feedback
                    (discussion_id, model, user_answer, feedback_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    discussion_id,
                    model,
                    user_answer,
                    json.dumps(feedback, ensure_ascii=False),
                    time.time(),
                ),
            )

    def record_assignment_feedback(
        self,
        question_id: int,
        model: str,
        answer_source: str,
        user_answer: str,
        feedback: dict[str, Any],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO assignment_feedback
                    (question_id, model, answer_source, user_answer, feedback_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    model,
                    answer_source,
                    user_answer,
                    json.dumps(feedback, ensure_ascii=False),
                    time.time(),
                ),
            )

    def wrong_attempts(self, bank: QuestionBank, limit: int = 80) -> list[dict[str, Any]]:
        questions = bank.by_id
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM attempts
                WHERE is_correct = 0 AND source IN ('bank', 'exam')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit * 4,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        seen: set[int] = set()
        for row in rows:
            if row["question_id"] in seen:
                continue
            question = questions.get(row["question_id"])
            if not question:
                continue
            seen.add(row["question_id"])
            items.append(
                {
                    "attempt_id": row["id"],
                    "question": public_question(question, include_answer=True),
                    "user_answer": json.loads(row["user_answer"]),
                    "created_at": row["created_at"],
                }
            )
            if len(items) >= limit:
                break
        return items

    def summary(self, source: str = "exam", user_id: int = 0) -> dict[str, int]:
        if source == "exam":
            where = "source IN ('bank', 'exam')"
            params: list[Any] = []
        else:
            where = "source = ?"
            params = [source]
        if user_id > 0:
            where += " AND user_id = ?"
            params.append(user_id)
        with self.connect() as db:
            row = db.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct,
                    SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS wrong
                FROM attempts
                WHERE {where}
                """,
                tuple(params),
            ).fetchone()
        return {
            "attempts": int(row["total"] or 0),
            "correct": int(row["correct"] or 0),
            "wrong": int(row["wrong"] or 0),
        }

    # ── 用户系统 ──

    def create_user(self, account: str, password: str, name: str, phone: str) -> dict[str, Any]:
        with self.connect() as db:
            existing = db.execute("SELECT id FROM users WHERE account = ?", (account,)).fetchone()
            if existing:
                raise ValueError("该账号已被注册。")
            password_hash = hash_password(password)
            now = time.time()
            role = "admin" if account == ADMIN_ACCOUNT else "student"
            status = "approved" if account == ADMIN_ACCOUNT else "pending"
            cursor = db.execute(
                """INSERT INTO users (account, password_hash, name, phone, role, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account, password_hash, name, phone, role, status, now),
            )
            user_id = cursor.lastrowid
            db.execute(
                """INSERT OR IGNORE INTO user_profile (user_id, updated_at)
                   VALUES (?, ?)""",
                (user_id, now),
            )
            return {
                "id": user_id,
                "account": account,
                "name": name,
                "phone": phone,
                "role": role,
                "status": status,
            }

    def authenticate(self, account: str, password: str, ip: str = "") -> dict[str, Any] | None:
        # 检查是否被锁定
        if self.is_account_locked(account):
            raise PermissionError("该账号因多次登录失败已被临时锁定，请30分钟后再试。")
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE account = ?",
                (account,),
            ).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                # 记录失败尝试
                self.record_login_attempt(account, ip, False)
                return None
            # 记录成功尝试
            self.record_login_attempt(account, ip, True)
            return {
                "id": row["id"],
                "account": row["account"],
                "name": row["name"],
                "phone": row["phone"],
                "role": row["role"],
                "status": row["status"],
            }

    def record_login_attempt(self, account: str, ip: str, success: bool) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO login_attempts (account, ip, success, created_at) VALUES (?, ?, ?, ?)",
                (account, ip, 1 if success else 0, time.time()),
            )

    def is_account_locked(self, account: str) -> bool:
        cutoff = time.time() - 1800  # 30 分钟窗口
        with self.connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS cnt FROM login_attempts
                   WHERE account = ? AND success = 0 AND created_at > ?
                   ORDER BY created_at DESC""",
                (account, cutoff),
            ).fetchone()
            if row and row["cnt"] >= 5:
                # 获取最近一次失败时间
                last = db.execute(
                    "SELECT created_at FROM login_attempts WHERE account = ? AND success = 0 ORDER BY created_at DESC LIMIT 1",
                    (account,),
                ).fetchone()
                if last and (time.time() - last["created_at"]) < 1800:
                    return True
            return False

    def cleanup_old_login_attempts(self) -> int:
        cutoff = time.time() - 3600  # 保留1小时
        with self.connect() as db:
            result = db.execute("DELETE FROM login_attempts WHERE created_at < ?", (cutoff,))
            return result.rowcount

    def create_session(self, user_id: int) -> str:
        token = generate_token()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, time.time()),
            )
        return token

    def get_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT s.token, s.user_id, s.created_at, u.account, u.name, u.role, u.status, u.phone
                   FROM sessions s JOIN users u ON s.user_id = u.id
                   WHERE s.token = ?""",
                (token,),
            ).fetchone()
            if not row:
                return None
            # 检查会话过期
            if time.time() - row["created_at"] > MAX_SESSION_AGE:
                db.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
            return {
                "token": row["token"],
                "user_id": row["user_id"],
                "account": row["account"],
                "name": row["name"],
                "role": row["role"],
                "status": row["status"],
                "phone": row["phone"],
            }

    def cleanup_expired_sessions(self) -> int:
        cutoff = time.time() - MAX_SESSION_AGE
        with self.connect() as db:
            result = db.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            return result.rowcount

    def delete_session(self, token: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    # ── 自定义题库 ──

    def create_custom_bank(self, name: str, owner_id: int, questions_json: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO custom_banks (name, owner_id, questions_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (name, owner_id, questions_json, time.time()),
            )
            return cursor.lastrowid

    def list_custom_banks(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb
                   JOIN users u ON cb.owner_id = u.id
                   WHERE cb.owner_id = ?
                   ORDER BY cb.created_at DESC""",
                (user_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "owner_id": row["owner_id"],
                    "owner_name": row["owner_name"],
                    "questions_json": row["questions_json"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def list_public_banks(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb
                   JOIN users u ON cb.owner_id = u.id
                   ORDER BY cb.created_at DESC LIMIT 100"""
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "owner_id": row["owner_id"],
                    "owner_name": row["owner_name"],
                    "questions_json": row["questions_json"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def get_custom_bank(self, bank_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb
                   JOIN users u ON cb.owner_id = u.id
                   WHERE cb.id = ?""",
                (bank_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "owner_id": row["owner_id"],
                "owner_name": row["owner_name"],
                "questions_json": row["questions_json"],
                "created_at": row["created_at"],
            }

    def get_pending_users(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, account, name, phone, role, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def approve_user(self, user_id: int, approved: bool) -> dict[str, Any]:
        status = "approved" if approved else "rejected"
        with self.connect() as db:
            db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            row = db.execute("SELECT id, account, name, phone, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise KeyError("用户不存在。")
            return dict(row)

    def get_all_users(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, account, name, phone, role, status, created_at FROM users ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    # ── 用户画像 ──

    def update_user_profile(self, user_id: int) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT a.is_correct, a.source, a.qtype, a.question_id
                   FROM attempts a WHERE a.user_id = ? AND a.source != 'ai'
                   ORDER BY a.created_at DESC LIMIT 500""",
                (user_id,),
            ).fetchall()

        total = len(rows)
        correct = sum(1 for r in rows if r["is_correct"])
        chapter_stats: dict[str, list[int]] = {}
        type_stats: dict[str, list[int]] = {}

        for r in rows:
            qtype = r["qtype"]
            if qtype not in type_stats:
                type_stats[qtype] = []
            type_stats[qtype].append(1 if r["is_correct"] else 0)

        chapter_accuracy = {
            ch: round(sum(vals) / len(vals), 3) if vals else 0
            for ch, vals in chapter_stats.items()
        }
        type_accuracy = {
            t: round(sum(vals) / len(vals), 3) if vals else 0
            for t, vals in type_stats.items()
        }

        # 找出弱项（正确率低于50%的章节/题型）
        weak_concepts = sorted(
            [ch for ch, acc in chapter_accuracy.items() if acc < 0.5],
            key=lambda ch: chapter_accuracy[ch],
        )[:5]
        strong_concepts = sorted(
            [ch for ch, acc in chapter_accuracy.items() if acc >= 0.8 and sum(chapter_stats.get(ch, [])) >= 5],
            key=lambda ch: -chapter_accuracy[ch],
        )[:5]

        now = time.time()
        with self.connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO user_profile
                   (user_id, chapter_accuracy_json, type_accuracy_json, weak_concepts_json,
                    strong_concepts_json, total_attempts, total_correct, last_practice_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    json.dumps(chapter_accuracy, ensure_ascii=False),
                    json.dumps(type_accuracy, ensure_ascii=False),
                    json.dumps(weak_concepts, ensure_ascii=False),
                    json.dumps(strong_concepts, ensure_ascii=False),
                    total,
                    correct,
                    now,
                    now,
                ),
            )

        return {
            "user_id": user_id,
            "total_attempts": total,
            "total_correct": correct,
            "accuracy": round(correct / total, 3) if total > 0 else 0,
            "type_accuracy": type_accuracy,
            "weak_concepts": weak_concepts,
            "strong_concepts": strong_concepts,
        }

    def get_user_profile(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM user_profile WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "chapter_accuracy": json.loads(row["chapter_accuracy_json"]),
                "type_accuracy": json.loads(row["type_accuracy_json"]),
                "weak_concepts": json.loads(row["weak_concepts_json"]),
                "strong_concepts": json.loads(row["strong_concepts_json"]),
                "total_attempts": row["total_attempts"],
                "total_correct": row["total_correct"],
                "practice_streak": row["practice_streak"],
                "last_practice_at": row["last_practice_at"],
            }

    # ── 去重 ──

    def is_question_duplicate(self, stem_hash: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM generated_questions WHERE stem_hash = ?", (stem_hash,)
            ).fetchone()
            return bool(row)

    def record_generated_question(self, stem_hash: str, question_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO generated_questions (stem_hash, question_id, created_at) VALUES (?, ?, ?)",
                (stem_hash, question_id, time.time()),
            )

    # ── AI 对话 ──

    def save_conversation(self, user_id: int, question_id: int | None, mode: str, messages: list[dict[str, str]]) -> int:
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO ai_conversations (user_id, question_id, mode, messages_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, question_id, mode, json.dumps(messages, ensure_ascii=False), now, now),
            )
            return cursor.lastrowid

    def get_conversations(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM ai_conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "question_id": row["question_id"],
                    "mode": row["mode"],
                    "messages": json.loads(row["messages_json"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def get_all_question_stems_and_hashes(self) -> list[dict[str, Any]]:
        """返回所有已存在的题目题干哈希（题库 + AI生成 + 已生成记录）"""
        hashes: set[str] = set()
        with self.connect() as db:
            rows = db.execute("SELECT stem_hash FROM ai_questions").fetchall()
            for row in rows:
                if row["stem_hash"]:
                    hashes.add(row["stem_hash"])
            rows = db.execute("SELECT stem_hash FROM generated_questions").fetchall()
            for row in rows:
                if row["stem_hash"]:
                    hashes.add(row["stem_hash"])
        return list(hashes)

    # ── 学习计划 ──

    def create_learning_plan(self, user_id: int, plan_data: dict[str, Any]) -> int:
        now = time.time()
        with self.connect() as db:
            # 删除旧计划
            db.execute("DELETE FROM learning_plans WHERE user_id = ?", (user_id,))
            cursor = db.execute(
                """INSERT INTO learning_plans (user_id, plan_data_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, json.dumps(plan_data, ensure_ascii=False), now, now),
            )
            return cursor.lastrowid

    def get_learning_plan(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM learning_plans WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            plan_data = json.loads(row["plan_data_json"])
            # 计算进度
            for day in plan_data.get("days", []):
                completed = 0
                for target in day.get("targets", []):
                    actual = db.execute(
                        """SELECT COUNT(*) AS cnt FROM attempts
                           WHERE user_id = ? AND source = ? AND created_at > ? AND created_at < ?""",
                        (user_id, target.get("source", "exam"), row["created_at"] + day.get("day_index", 0) * 86400,
                         row["created_at"] + (day.get("day_index", 0) + 1) * 86400),
                    ).fetchone()
                    target["completed"] = actual["cnt"] if actual else 0
                    completed += min(target["completed"], target.get("target_count", 0))
                total_target = sum(t.get("target_count", 0) for t in day.get("targets", []))
                day["progress"] = round(completed / total_target, 3) if total_target > 0 else 0
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "plan_data": plan_data,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    # ── 社区 ──

    def create_post(self, user_id: int, question_id: int | None, bank_id: str | None,
                    title: str, content: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO community_posts (user_id, question_id, bank_id, title, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, question_id, bank_id, title, content, time.time()),
            )
            return cursor.lastrowid

    def get_posts(self, question_id: int | None = None, bank_id: str | None = None,
                  limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as db:
            conditions = []
            params: list[Any] = []
            if question_id is not None:
                conditions.append("p.question_id = ?")
                params.append(question_id)
            if bank_id is not None:
                conditions.append("p.bank_id = ?")
                params.append(bank_id)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.extend([limit, offset])
            rows = db.execute(
                f"""SELECT p.*, u.name AS author_name, u.account AS author_account
                    FROM community_posts p
                    JOIN users u ON p.user_id = u.id
                    {where}
                    ORDER BY p.created_at DESC
                    LIMIT ? OFFSET ?""",
                params,
            ).fetchall()
            posts = []
            for row in rows:
                replies = db.execute(
                    """SELECT r.*, u.name AS author_name, u.account AS author_account
                       FROM community_replies r
                       JOIN users u ON r.user_id = u.id
                       WHERE r.post_id = ? ORDER BY r.created_at ASC""",
                    (row["id"],),
                ).fetchall()
                posts.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "author_name": row["author_name"],
                    "author_account": row["author_account"],
                    "question_id": row["question_id"],
                    "bank_id": row["bank_id"],
                    "title": row["title"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "replies": [
                        {
                            "id": r["id"],
                            "post_id": r["post_id"],
                            "user_id": r["user_id"],
                            "author_name": r["author_name"],
                            "author_account": r["author_account"],
                            "content": r["content"],
                            "created_at": r["created_at"],
                        }
                        for r in replies
                    ],
                })
            return posts

    def create_reply(self, post_id: int, user_id: int, content: str) -> int:
        with self.connect() as db:
            # 验证帖子存在
            post = db.execute("SELECT id FROM community_posts WHERE id = ?", (post_id,)).fetchone()
            if not post:
                raise KeyError("帖子不存在。")
            cursor = db.execute(
                """INSERT INTO community_replies (post_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (post_id, user_id, content, time.time()),
            )
            return cursor.lastrowid

    # ── 排行榜 ──

    def get_leaderboard(self, period: str = "week") -> list[dict[str, Any]]:
        if period == "month":
            cutoff = time.time() - 86400 * 30
        else:
            cutoff = time.time() - 86400 * 7
        with self.connect() as db:
            rows = db.execute(
                """SELECT a.user_id, u.name, u.account,
                          COUNT(*) AS practice_count,
                          SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
                   FROM attempts a
                   JOIN users u ON a.user_id = u.id
                   WHERE a.created_at > ? AND a.user_id > 0
                   GROUP BY a.user_id
                   ORDER BY practice_count DESC
                   LIMIT 50""",
                (cutoff,),
            ).fetchall()
            return [
                {
                    "rank": i + 1,
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "account": row["account"],
                    "practice_count": row["practice_count"],
                    "correct_count": row["correct_count"],
                    "accuracy": round(row["correct_count"] / row["practice_count"], 3)
                    if row["practice_count"] > 0 else 0,
                }
                for i, row in enumerate(rows)
            ]

    # ── 学习报告 ──

    def get_learning_report_data(self, user_id: int) -> dict[str, Any]:
        profile = self.get_user_profile(user_id) or {}
        with self.connect() as db:
            user = db.execute(
                "SELECT name, account, created_at FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            # 章节正确率
            chapter_rows = db.execute(
                """SELECT a.is_correct, a.source
                   FROM attempts a WHERE a.user_id = ? AND a.source != 'ai'
                   ORDER BY a.created_at DESC LIMIT 200""",
                (user_id,),
            ).fetchall()
            # 近期练习
            recent = db.execute(
                """SELECT a.* FROM attempts a
                   WHERE a.user_id = ? ORDER BY a.created_at DESC LIMIT 20""",
                (user_id,),
            ).fetchall()
            # 题型正确率
            type_rows = db.execute(
                """SELECT a.qtype, a.is_correct, COUNT(*) AS cnt
                   FROM attempts a WHERE a.user_id = ? AND a.source != 'ai'
                   GROUP BY a.qtype, a.is_correct""",
                (user_id,),
            ).fetchall()

        total_attempts = sum(r["cnt"] for r in type_rows)
        total_correct = sum(r["cnt"] for r in type_rows if r["is_correct"])

        type_accuracy: dict[str, dict[str, int]] = {}
        for r in type_rows:
            qtype = r["qtype"]
            if qtype not in type_accuracy:
                type_accuracy[qtype] = {"correct": 0, "total": 0}
            type_accuracy[qtype]["total"] += r["cnt"]
            if r["is_correct"]:
                type_accuracy[qtype]["correct"] += r["cnt"]

        return {
            "user": {
                "name": user["name"] if user else "",
                "account": user["account"] if user else "",
                "member_since": user["created_at"] if user else 0,
            },
            "stats": {
                "total_attempts": total_attempts,
                "total_correct": total_correct,
                "overall_accuracy": round(total_correct / total_attempts, 3) if total_attempts > 0 else 0,
            },
            "type_accuracy": {
                t: {
                    "accuracy": round(d["correct"] / d["total"], 3) if d["total"] > 0 else 0,
                    "total": d["total"],
                    "correct": d["correct"],
                }
                for t, d in type_accuracy.items()
            },
            "weak_concepts": profile.get("weak_concepts", []),
            "strong_concepts": profile.get("strong_concepts", []),
            "recent_practice": [
                {
                    "question_id": r["question_id"],
                    "qtype": r["qtype"],
                    "is_correct": r["is_correct"],
                    "created_at": r["created_at"],
                }
                for r in recent
            ],
        }


def public_question(question: ObjectiveQuestion, include_answer: bool = False) -> dict[str, Any]:
    supplement = option_supplement_for(question)
    options = [dict(option) for option in question.options]
    if supplement:
        by_key = {option.get("key", ""): option for option in options}
        for key in supplement["options"]:
            if key not in by_key:
                option = {"key": key, "text": ""}
                options.append(option)
                by_key[key] = option
        options.sort(key=lambda item: item.get("key", ""))
        for option in options:
            key = option.get("key", "")
            if key in supplement["options"]:
                option["raw_text"] = option.get("text", "")
                option["text"] = supplement["options"][key]
                option["ai_supplemented"] = option["raw_text"] != option["text"]
    payload = {
        "bank_id": "exam",
        "id": question.id,
        "source_order": question.source_order,
        "source_num": question.source_num,
        "qtype": question.qtype,
        "chapter": question.chapter,
        "stem": question.stem,
        "options": options,
        "score": question.score,
        "images": question.images,
        "repaired": question.repaired,
        "suspicious": question.suspicious,
        "stem_hash": question.stem_hash,
        "ai_completed": bool(supplement),
        "completion_note": supplement["note"] if supplement else "",
    }
    if supplement:
        payload["original_options"] = question.options
    if include_answer:
        payload["answer"] = question.answer
        payload["raw_correct"] = question.raw_correct
    return payload


def public_assignment_question(question: AssignmentQuestion, include_answer: bool = True) -> dict[str, Any]:
    payload = {
        "bank_id": "assignment",
        "id": question.id,
        "source_order": question.source_order,
        "source_num": question.source_num,
        "qtype": question.qtype,
        "chapter": question.chapter,
        "stem": question.stem,
        "options": [dict(option) for option in question.options],
        "images": question.images,
        "suspicious": question.suspicious,
        "stem_hash": question.stem_hash,
        "answer_source": question.answer_source,
        "answer_available": bool(question.answer),
    }
    if include_answer:
        payload["answer"] = question.answer
        payload["raw_correct"] = question.raw_correct
    return payload


def public_discussion(question: DiscussionQuestion) -> dict[str, Any]:
    return {
        "id": question.id,
        "source_order": question.source_order,
        "chapter": question.chapter,
        "prompt": question.prompt,
        "stem_hash": question.stem_hash,
    }


def exam_bank_stats(bank: QuestionBank, db: PracticeDatabase) -> dict[str, Any]:
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
        "bank_id": bank.bank_id,
        "label": bank.label,
        "docx": {
            "path": bank.docx_path,
            "sha256": bank.docx_sha256,
        },
        "counts": {
            "objective": len(bank.questions),
            "discussion": len(bank.discussions),
            "image_questions": image_questions,
            "repaired_answers": repaired,
            "suspicious_questions": suspicious,
            "ai_completed_questions": sum(1 for question in bank.questions if option_supplement_for(question)),
        },
        "type_counts": type_counts,
        "chapters": chapters,
        "audit": bank.audit,
        "integrity": integrity,
        "practice": db.summary("exam"),
    }


def assignment_bank_stats(bank: AssignmentBank, db: PracticeDatabase) -> dict[str, Any]:
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
        "bank_id": bank.bank_id,
        "label": bank.label,
        "docx": {
            "path": bank.docx_path,
            "sha256": bank.docx_sha256,
        },
        "counts": {
            "questions": len(bank.questions),
            "image_questions": image_questions,
            "word_answers": word_answers,
            "ai_reference_answers": ai_references,
            "missing_answers": len(missing_answers),
        },
        "type_counts": type_counts,
        "chapters": chapters,
        "audit": bank.audit,
        "integrity": integrity,
        "practice": db.summary("assignment"),
    }


def stats_payload(exam_bank: QuestionBank, assignment_bank: AssignmentBank, db: PracticeDatabase) -> dict[str, Any]:
    exam = exam_bank_stats(exam_bank, db)
    assignment = assignment_bank_stats(assignment_bank, db)
    config = config_payload()
    payload = {
        **exam,
        "banks": {
            "exam": exam,
            "assignment": assignment,
        },
        "models": config["models"],
        "providers": config["providers"],
        "default_provider": config["default_provider"],
        "default_model": config["default_model"],
        "ai_configured": config["ai_configured"],
        "api_key_source": config["api_key_source"],
        "key_preview": config["key_preview"],
        "timeout_seconds": config["timeout_seconds"],
    }
    return payload


def public_bank_question(question: ObjectiveQuestion | AssignmentQuestion, include_answer: bool = False) -> dict[str, Any]:
    if isinstance(question, AssignmentQuestion):
        return public_assignment_question(question, include_answer=True)
    return public_question(question, include_answer=include_answer)


def filter_questions(bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> list[ObjectiveQuestion | AssignmentQuestion]:
    types = set(payload.get("types") or [])
    chapters = set(payload.get("chapters") or [])
    questions = []
    for question in bank.questions:
        if types and question.qtype not in types:
            continue
        if chapters and question.chapter not in chapters:
            continue
        questions.append(question)
    return questions


def create_session(bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "sequence")
    if payload.get("question_ids"):
        id_order = [int(item) for item in payload.get("question_ids") or []]
        questions = [bank.by_id[item] for item in id_order if item in bank.by_id]
    else:
        questions = filter_questions(bank, payload)
    requested_count = payload.get("count")
    if requested_count in (None, "", 0, "0", "all"):
        count = len(questions)
    else:
        count = max(1, min(int(requested_count), len(questions))) if questions else 0
    if mode == "random":
        selected = random.sample(questions, count) if count else []
    else:
        selected = questions[:count]
    return {
        "session_id": str(uuid.uuid4()),
        "bank_id": bank.bank_id,
        "mode": mode,
        "total_available": len(questions),
        "count": len(selected),
        "questions": [public_bank_question(question) for question in selected],
    }


def generate_learning_plan_data(
    bank: QuestionBank, db: PracticeDatabase, user_id: int
) -> dict[str, Any]:
    """根据用户画像生成7天学习计划"""
    profile = db.get_user_profile(user_id) or {}
    weak_concepts = profile.get("weak_concepts", [])
    type_accuracy = profile.get("type_accuracy", {})
    weak_types = [t for t, acc in type_accuracy.items() if acc < 0.5]

    plan_days = []
    daily_targets = {
        "单选题": 10,
        "多选题": 5,
        "填空题": 5,
        "判断题": 5,
    }

    chapter_questions: dict[str, int] = {}
    for q in bank.questions:
        chapter_questions[q.chapter] = chapter_questions.get(q.chapter, 0) + 1

    recommendations_by_chapter: dict[str, list[str]] = {}
    for ch, acc in (profile.get("chapter_accuracy", {}) or {}).items():
        if acc < 0.5:
            recommendations_by_chapter[ch] = ["重点复习该章节基础概念", "完成该章节练习并查看解析"]
        elif acc < 0.7:
            recommendations_by_chapter[ch] = ["巩固该章节中等难度题目", "回顾错题中的知识点"]
        else:
            recommendations_by_chapter[ch] = ["保持练习，尝试变体题目"]

    for day in range(7):
        day_targets = []
        for qtype, count in daily_targets.items():
            day_targets.append({
                "qtype": qtype,
                "target_count": count,
                "source": "exam",
                "completed": 0,
            })
        focus_chapter = weak_concepts[day % len(weak_concepts)] if weak_concepts else bank.questions[0].chapter if bank.questions else "未分章"
        plan_days.append({
            "day_index": day,
            "day_label": f"第{day + 1}天",
            "focus_chapter": focus_chapter,
            "focus_types": weak_types[:2] if weak_types else ["单选题", "填空题"],
            "targets": day_targets,
            "recommendations": recommendations_by_chapter.get(focus_chapter, ["完成每日练习目标", "回顾当日错题"]),
            "progress": 0,
        })

    return {
        "days": plan_days,
        "total_days": 7,
        "profile_summary": {
            "weak_concepts": weak_concepts,
            "weak_types": weak_types,
            "overall_accuracy": profile.get("accuracy", 0),
        },
    }


def normalize_provider(provider: str | None) -> str:
    provider = (provider or str(RUNTIME_CONFIG.get("default_provider") or "zhipu")).strip().lower()
    if provider not in AI_PROVIDERS:
        raise ValueError(f"不支持的 AI 服务商: {provider}")
    return provider


def provider_for_model(model: str) -> str:
    for provider_id, config in AI_PROVIDERS.items():
        if model in config["models"]:
            return provider_id
    raise ValueError(f"不支持的模型: {model}")


def normalize_model(model: str | None, provider: str | None = None) -> str:
    if not model:
        return current_default_model()
    model = MODEL_ALIASES.get(str(model).strip(), str(model).strip())
    if model not in ALLOWED_MODELS:
        raise ValueError(f"不支持的模型: {model}")
    if provider and model not in AI_PROVIDERS[normalize_provider(provider)]["models"]:
        raise ValueError(f"{AI_PROVIDERS[normalize_provider(provider)]['label']} 不支持模型: {model}")
    return model


def current_default_model() -> str:
    raw = MODEL_ALIASES.get(str(RUNTIME_CONFIG.get("default_model") or "").strip(), str(RUNTIME_CONFIG.get("default_model") or "").strip())
    if raw in ALLOWED_MODELS:
        return raw
    provider = normalize_provider(str(RUNTIME_CONFIG.get("default_provider") or "zhipu"))
    return str(AI_PROVIDERS[provider]["default_model"])


def ai_api_key(provider: str) -> str:
    provider = normalize_provider(provider)
    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    runtime_key = str(runtime_keys.get(provider) or "").strip()
    if runtime_key:
        return runtime_key
    for env_name in AI_PROVIDERS[provider]["env"]:
        value = os.environ.get(env_name)
        if value:
            return value.strip()
    return ""


def deepseek_api_key() -> str:
    return ai_api_key("deepseek")


def api_key_source(provider: str | None = None) -> str:
    provider = normalize_provider(provider or provider_for_model(current_default_model()))
    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    if str(runtime_keys.get(provider) or "").strip():
        return "runtime"
    if any(os.environ.get(env_name) for env_name in AI_PROVIDERS[provider]["env"]):
        return "environment"
    return "none"


def key_preview(provider: str | None = None) -> str:
    provider = normalize_provider(provider or provider_for_model(current_default_model()))
    key = ai_api_key(provider)
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def provider_payload(provider_id: str) -> dict[str, Any]:
    config = AI_PROVIDERS[provider_id]
    return {
        "id": provider_id,
        "label": config["label"],
        "models": config["models"],
        "default_model": config["default_model"],
        "ai_configured": bool(ai_api_key(provider_id)),
        "api_key_source": api_key_source(provider_id),
        "key_preview": key_preview(provider_id),
    }


def config_payload() -> dict[str, Any]:
    model = current_default_model()
    provider = provider_for_model(model)
    return {
        "models": sorted(ALLOWED_MODELS),
        "providers": [provider_payload(provider_id) for provider_id in AI_PROVIDERS],
        "default_provider": provider,
        "default_model": model,
        "ai_configured": bool(ai_api_key(provider)),
        "api_key_source": api_key_source(provider),
        "key_preview": key_preview(provider),
        "timeout_seconds": AI_TIMEOUT_SECONDS,
    }


def update_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider = normalize_provider(payload.get("provider") or payload.get("default_provider") or RUNTIME_CONFIG.get("default_provider"))
    if "model" in payload or "default_model" in payload:
        model = normalize_model(payload.get("model") or payload.get("default_model"), provider=None)
        provider = provider_for_model(model)
        RUNTIME_CONFIG["default_provider"] = provider
        RUNTIME_CONFIG["default_model"] = model
    elif "provider" in payload or "default_provider" in payload:
        RUNTIME_CONFIG["default_provider"] = provider
        if current_default_model() not in AI_PROVIDERS[provider]["models"]:
            RUNTIME_CONFIG["default_model"] = AI_PROVIDERS[provider]["default_model"]

    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    for provider_id in AI_PROVIDERS:
        key_name = f"{provider_id}_api_key"
        if key_name in payload:
            api_key = str(payload.get(key_name) or "").strip()
            if api_key:
                runtime_keys[provider_id] = api_key
    if "api_keys" in payload and isinstance(payload["api_keys"], dict):
        for provider_id, value in payload["api_keys"].items():
            if provider_id in AI_PROVIDERS and str(value or "").strip():
                runtime_keys[provider_id] = str(value).strip()
    if "api_key" in payload:
        api_key = str(payload.get("api_key") or "").strip()
        if api_key:
            runtime_keys[provider] = api_key
    clear_provider = payload.get("clear_provider")
    if clear_provider:
        runtime_keys[normalize_provider(clear_provider)] = ""
    elif payload.get("clear_api_key"):
        runtime_keys[provider] = ""
    return config_payload()


class AIProviderError(RuntimeError):
    pass


class DeepSeekError(AIProviderError):
    pass


def ai_error_message(provider: str, message: str) -> str:
    return f"{AI_PROVIDERS[provider]['label']} {message}"


def build_ai_request(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    json_mode: bool,
    max_tokens: int,
    stream: bool = False,
) -> tuple[str, request.Request]:
    model = normalize_model(model)
    provider = provider_for_model(model)
    api_key = ai_api_key(provider)
    if not api_key:
        raise AIProviderError(f"未设置 {AI_PROVIDERS[provider]['label']} API Key，AI 功能暂不可用。")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if stream:
        payload["stream"] = True
    req = request.Request(
        str(AI_PROVIDERS[provider]["url"]),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        },
        method="POST",
    )
    return provider, req


def read_ai_error(exc: error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace")
    try:
        error_payload = json.loads(detail)
        return error_payload.get("error", {}).get("message") or detail
    except json.JSONDecodeError:
        return detail


def ai_content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(ai_content_to_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            if key in value:
                text = ai_content_to_text(value.get(key))
                if text:
                    return text
        return ""
    return str(value)


def ai_choice_text(choice: dict[str, Any]) -> str:
    visible_chunks: list[str] = []
    fallback_chunks: list[str] = []
    for container_key in ("message", "delta"):
        container = choice.get(container_key)
        if not isinstance(container, dict):
            continue
        for field in ("content", "text"):
            text = ai_content_to_text(container.get(field))
            if text:
                visible_chunks.append(text)
        text = ai_content_to_text(container.get("reasoning_content"))
        if text:
            fallback_chunks.append(text)
    for field in ("content", "text"):
        text = ai_content_to_text(choice.get(field))
        if text:
            visible_chunks.append(text)
    if not visible_chunks:
        for field in ("reasoning_content", "reasoning"):
            text = ai_content_to_text(choice.get(field))
            if text:
                fallback_chunks.append(text)
    return "".join(visible_chunks or fallback_chunks)


def ai_response_text(data: dict[str, Any], provider: str) -> str:
    try:
        choices = data["choices"]
        if not choices:
            raise IndexError
        text = ai_choice_text(choices[0])
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError(ai_error_message(provider, f"响应格式异常: {data}")) from exc
    if not text:
        raise AIProviderError(ai_error_message(provider, f"响应内容为空: {data}"))
    return text


def call_ai(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.2,
    json_mode: bool = False,
    retry_without_json_mode: bool = True,
    max_tokens: int = 1200,
    _retry_count: int = 0,
) -> str:
    provider, req = build_ai_request(messages, model, temperature, json_mode, max_tokens)
    try:
        with DEEPSEEK_OPENER.open(req, timeout=AI_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        message = read_ai_error(exc)
        if json_mode and retry_without_json_mode:
            return call_ai(messages, model, temperature, False, False, max_tokens)
        if exc.code == 429:
            if _retry_count < AI_MAX_RETRIES:
                time.sleep(2 ** _retry_count)
                return call_ai(messages, model, temperature, json_mode, retry_without_json_mode, max_tokens, _retry_count + 1)
            raise AIProviderError(ai_error_message(provider, f"接口触发频率限制，请稍后重试或切换模型。详情：{message}")) from exc
        raise AIProviderError(ai_error_message(provider, f"接口返回错误 {exc.code}: {message}")) from exc
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIProviderError(ai_error_message(provider, "接口请求超时，请切换模型或稍后重试。")) from exc
        raise AIProviderError(ai_error_message(provider, f"接口连接失败: {exc.reason}")) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AIProviderError(ai_error_message(provider, "接口请求超时，请切换模型或稍后重试。")) from exc

    return ai_response_text(data, provider)


def call_deepseek(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.2,
    json_mode: bool = False,
    retry_without_json_mode: bool = True,
    max_tokens: int = 1200,
    _retry_count: int = 0,
) -> str:
    return call_ai(messages, model, temperature, json_mode, retry_without_json_mode, max_tokens, _retry_count)


def call_ai_stream(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1600,
) -> Any:
    provider, req = build_ai_request(messages, model, temperature, False, max_tokens, stream=True)
    try:
        with DEEPSEEK_OPENER.open(req, timeout=AI_TIMEOUT_SECONDS) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                for choice in data.get("choices", []):
                    content = ai_choice_text(choice)
                    if content:
                        yield content
    except error.HTTPError as exc:
        message = read_ai_error(exc)
        if exc.code == 429:
            raise AIProviderError(ai_error_message(provider, f"接口触发频率限制，请稍后重试或切换模型。详情：{message}")) from exc
        raise AIProviderError(ai_error_message(provider, f"接口返回错误 {exc.code}: {message}")) from exc
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIProviderError(ai_error_message(provider, "接口请求超时，请切换模型或稍后重试。")) from exc
        raise AIProviderError(ai_error_message(provider, f"接口连接失败: {exc.reason}")) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AIProviderError(ai_error_message(provider, "接口请求超时，请切换模型或稍后重试。")) from exc


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def safe_ai_seed_questions(bank: QuestionBank) -> list[ObjectiveQuestion]:
    return [
        question
        for question in bank.questions
        if not any("疑似" in note or "为空" in note for note in question.suspicious)
    ]


def generate_ai_question(bank: QuestionBank, db: PracticeDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    model = normalize_model(payload.get("model"))
    qtype = payload.get("qtype") or "单选题"
    if qtype not in {"单选题", "多选题", "填空题", "判断题"}:
        raise ValueError("AI 出题题型不支持。")

    user_id = payload.get("user_id", 0)
    # 获取用户弱项信息
    user_context = ""
    if user_id > 0:
        profile = db.get_user_profile(user_id)
        if profile and profile.get("weak_concepts"):
            weak = profile["weak_concepts"]
            weak_types = [t for t, acc in profile.get("type_accuracy", {}).items() if acc < 0.5]
            user_context = f"\n学生弱项章节：{', '.join(weak)}。薄弱题型：{', '.join(weak_types) if weak_types else '无'}。请针对薄弱知识点出题。"

    source_id = payload.get("source_question_id")
    source: ObjectiveQuestion | None = None
    if source_id:
        source = bank.by_id.get(int(source_id))
    if not source:
        seeds = safe_ai_seed_questions(bank)
        same_type = [item for item in seeds if item.qtype == qtype]
        source = random.choice(same_type or seeds)

    # 获取已有题目哈希用于去重
    existing_hashes = db.get_all_question_stems_and_hashes()

    prompt = {
        "source_question": public_question(source, include_answer=True),
        "target_type": qtype,
        "existing_stems_hashes": existing_hashes[:50],  # 传一部分哈希防止重复
        "requirements": [
            "根据 source_question 的知识点生成一道全新的数据结构期末练习题。",
            "不要照抄原题数字和问法。确保生成的题目与任何已有题目都不重复。",
            "必须输出 JSON 对象，不要 Markdown。",
            "字段必须包含 qtype, stem, options, answer, analysis。",
            "stem 和 analysis 可以使用 Markdown 表格、行内公式 $...$、代码块和列表来表达公式、矩阵、复杂度或步骤。",
            "选择题 options 使用 A, B, C, D；判断题用 A=对, B=错。",
            "填空题 options 为空数组，answer 为可直接批改的标准答案。",
            user_context if user_context else "",
        ],
    }
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是数据结构期末考试命题老师，只输出可解析 JSON。绝不生成与已有题目相同或高度相似的题目。",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        model=model,
        temperature=0.25,
        json_mode=True,
        max_tokens=900,
    )
    item = extract_json_object(content)
    item = normalize_ai_item(item, qtype)
    validate_ai_item(item)

    # 去重检查
    stem_hash = text_hash(item["stem"])
    if db.is_question_duplicate(stem_hash):
        raise ValueError("AI 生成的题目与已有题目重复，请重新生成。")

    verify_ai_item(item, source, model)
    ai_id = db.record_ai_question(item, model, source.id)
    db.record_generated_question(stem_hash, ai_id)
    return {
        "id": ai_id,
        "model": model,
        "source_question_id": source.id,
        "question": {
            "id": ai_id,
            "qtype": item["qtype"],
            "stem": item["stem"],
            "options": item.get("options", []),
            "analysis": item.get("analysis", ""),
        },
    }


def normalize_ai_item(item: dict[str, Any], fallback_type: str) -> dict[str, Any]:
    qtype = item.get("qtype") or item.get("type") or fallback_type
    options = item.get("options") or []
    if isinstance(options, dict):
        options = [{"key": key, "text": str(value)} for key, value in options.items()]
    normalized_options = []
    for option in options:
        if isinstance(option, dict):
            key = str(option.get("key") or option.get("label") or "").strip().upper()
            text = str(option.get("text") or option.get("value") or "").strip()
        else:
            match = OPTION_RE.match(str(option).strip())
            key = match.group(1) if match else ""
            text = match.group(2) if match else str(option)
        if key:
            normalized_options.append({"key": key, "text": text})
    answer = item.get("answer") or item.get("correct_answer") or item.get("correctAnswer") or ""
    if isinstance(answer, list):
        answer = "".join(str(part) for part in answer)
    return {
        "qtype": qtype,
        "stem": str(item.get("stem") or item.get("question") or "").strip(),
        "options": normalized_options,
        "answer": str(answer).strip(),
        "analysis": str(item.get("analysis") or item.get("explanation") or "").strip(),
    }


def validate_ai_item(item: dict[str, Any]) -> None:
    if item["qtype"] not in {"单选题", "多选题", "填空题", "判断题"}:
        raise DeepSeekError("AI 生成题型不合法。")
    if len(item["stem"]) < 8:
        raise DeepSeekError("AI 生成题干过短。")
    if not item["answer"]:
        raise DeepSeekError("AI 生成答案为空。")
    if item["qtype"] in {"单选题", "多选题", "判断题"}:
        keys = {option["key"] for option in item["options"]}
        if len(keys) < 2:
            raise DeepSeekError("AI 选择题选项不足。")
        answer_keys = set(normalize_choice_answer(item["answer"]))
        if not answer_keys or not answer_keys.issubset(keys):
            raise DeepSeekError("AI 答案不在选项中。")
    if item["qtype"] == "填空题" and item["options"]:
        raise DeepSeekError("AI 填空题不应包含选项。")


def verify_ai_item(item: dict[str, Any], source: ObjectiveQuestion, model: str) -> None:
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是数据结构题目质检员，只输出 JSON。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "检查生成题是否知识点清楚且答案正确。",
                        "source_question": public_question(source, include_answer=True),
                        "generated_question": item,
                        "output_schema": {
                            "valid": True,
                            "answer": "标准答案",
                            "reason": "简短理由",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=model,
        temperature=0.0,
        json_mode=True,
        max_tokens=500,
    )
    verdict = extract_json_object(content)
    if not verdict.get("valid"):
        raise DeepSeekError(f"AI 二次校验未通过: {verdict.get('reason', '')}")
    checked_answer = str(verdict.get("answer") or "").strip()
    if checked_answer:
        if item["qtype"] == "多选题":
            same = normalize_multi_answer(checked_answer) == normalize_multi_answer(item["answer"])
        elif item["qtype"] in {"单选题", "判断题"}:
            same = normalize_choice_answer(checked_answer) == normalize_choice_answer(item["answer"])
        else:
            same = normalize_fill(checked_answer) in fill_candidates(item["answer"])
        if not same:
            raise DeepSeekError("AI 二次校验答案与生成答案不一致。")


def grade_ai_answer(db: PracticeDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    ai_id = str(payload.get("ai_question_id") or payload.get("id") or "")
    item = db.get_ai_question(ai_id)
    if not item:
        raise KeyError("AI 题不存在。")
    pseudo_question = ObjectiveQuestion(
        id=0,
        source_order=0,
        source_num="AI",
        qtype=item["qtype"],
        chapter="AI 出题",
        stem=item["stem"],
        options=item["options"],
        answer=item["answer"],
        raw_correct=item["answer"],
        score=None,
    )
    result = grade_answer(pseudo_question, payload.get("answer"))
    db.record_attempt(0, "ai", item["qtype"], payload.get("answer"), item["answer"], result["is_correct"])
    result["analysis"] = item.get("analysis") or result["analysis"]
    return result


def grade_discussion(bank: QuestionBank, db: PracticeDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    discussion_id = int(payload.get("discussion_id"))
    discussion = bank.discussion_by_id.get(discussion_id)
    if not discussion:
        raise KeyError("讨论题不存在。")
    answer = str(payload.get("answer") or "").strip()
    if len(answer) < 4:
        raise ValueError("请先写出你的回答。")
    model = normalize_model(payload.get("model"))
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是数据结构课程助教，只输出 JSON，给出参考批改而不是绝对判分。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "discussion_question": public_discussion(discussion),
                        "student_answer": answer,
                        "output_schema": {
                            "score": 0,
                            "level": "需要加强/基本到位/较好",
                            "reference_answer": "参考答案，必要时使用 Markdown 表格、公式 $...$、代码块或列表",
                            "covered_points": ["已覆盖要点"],
                            "missing_points": ["缺失要点"],
                            "suggestion": "下一步复习建议",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=model,
        temperature=0.2,
        json_mode=True,
        max_tokens=1400,
    )
    feedback = extract_json_object(content)
    feedback.setdefault("score", 0)
    feedback.setdefault("level", "参考反馈")
    feedback.setdefault("covered_points", [])
    feedback.setdefault("missing_points", [])
    feedback.setdefault("reference_answer", "")
    feedback.setdefault("suggestion", "")
    db.record_discussion_feedback(discussion_id, model, answer, feedback)
    return {"discussion": public_discussion(discussion), "feedback": feedback}


def grade_assignment(bank: AssignmentBank, db: PracticeDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    question_id = int(payload.get("question_id") or payload.get("assignment_id"))
    question = bank.by_id.get(question_id)
    if not question:
        raise KeyError("作业题不存在。")
    answer = str(payload.get("answer") or "").strip()
    if len(answer) < 2:
        raise ValueError("请先写出你的回答。")
    if not question.answer:
        raise ValueError("本题没有可用参考答案。")
    model = normalize_model(payload.get("model"))
    source_label = "Word正确答案" if question.answer_source == "word_answer" else "AI参考答案"
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是数据结构课程助教，只输出 JSON。按参考答案给学习建议，不把AI参考答案说成官方答案。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "assignment_question": public_assignment_question(question, include_answer=True),
                        "reference_source": source_label,
                        "student_answer": answer,
                        "output_schema": {
                            "score": 0,
                            "level": "需要加强/基本到位/较好",
                            "verdict": "简短结论",
                            "reference_answer": "参考答案，必要时使用 Markdown 表格、公式 $...$、代码块或列表",
                            "covered_points": ["已覆盖要点"],
                            "missing_points": ["缺失要点"],
                            "suggestion": "下一步复习建议",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=model,
        temperature=0.2,
        json_mode=True,
        max_tokens=1500,
    )
    feedback = extract_json_object(content)
    feedback.setdefault("score", 0)
    feedback.setdefault("level", "参考反馈")
    feedback.setdefault("verdict", "")
    feedback.setdefault("covered_points", [])
    feedback.setdefault("missing_points", [])
    feedback.setdefault("reference_answer", question.answer)
    feedback.setdefault("suggestion", "")
    db.record_assignment_feedback(question_id, model, question.answer_source, answer, feedback)
    return {
        "question": public_assignment_question(question, include_answer=True),
        "answer_source": question.answer_source,
        "feedback": feedback,
    }


def supplements_payload(exam_bank: QuestionBank, assignment_bank: AssignmentBank) -> dict[str, Any]:
    items = []
    seen_exam: set[int] = set()
    for question in exam_bank.questions:
        supplement = option_supplement_for(question)
        if not supplement or question.id in seen_exam:
            continue
        seen_exam.add(question.id)
        items.append(
            {
                "bank_id": "exam",
                "kind": "option_supplement",
                "question_id": question.id,
                "chapter": question.chapter,
                "qtype": question.qtype,
                "stem": question.stem,
                "answer": question.answer,
                "options": supplement["options"],
                "note": supplement["note"],
            }
        )
    for question in assignment_bank.questions:
        if question.answer_source != "ai_reference":
            continue
        items.append(
            {
                "bank_id": "assignment",
                "kind": "ai_reference_answer",
                "question_id": question.id,
                "chapter": question.chapter,
                "qtype": question.qtype,
                "stem": question.stem,
                "answer": question.answer,
                "note": "Word 正确答案为空，使用 AI参考答案。",
            }
        )
    return {"items": items, "count": len(items)}


def ai_supplement_question(bank: QuestionBank, payload: dict[str, Any]) -> dict[str, Any]:
    question_id = int(payload.get("question_id"))
    question = bank.by_id.get(question_id)
    if not question:
        raise KeyError("题目不存在。")
    model = normalize_model(payload.get("model"))
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是数据结构题库修复员。只输出 JSON，不修改标准答案。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "根据题干、现有选项、正确答案，补全缺失或残缺的选项文本，并说明依据。不要改变正确答案。",
                        "question": public_question(question, include_answer=True),
                        "output_schema": {
                            "options": {"A": "补全后的选项", "B": "补全后的选项"},
                            "reason": "补全依据",
                            "confidence": "high/medium/low",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=model,
        temperature=0.0,
        json_mode=True,
        max_tokens=900,
    )
    suggestion = extract_json_object(content)
    options = suggestion.get("options") or {}
    if not isinstance(options, dict):
        raise DeepSeekError("AI 补全结果格式不合法。")
    correct = normalize_choice_answer(question.answer)
    if question.qtype in {"单选题", "多选题", "判断题"} and correct:
        option_keys = {key.upper() for key in options.keys()}
        if not set(correct).issubset(option_keys):
            raise DeepSeekError("AI 补全结果没有包含标准答案对应选项。")
    return {
        "question": public_question(question, include_answer=True),
        "suggestion": suggestion,
    }


def question_ai_request(bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> dict[str, Any]:
    question_id = int(payload.get("question_id"))
    question = bank.by_id.get(question_id)
    if not question:
        raise KeyError("题目不存在。")
    mode = str(payload.get("mode") or "explain").strip()
    message = str(payload.get("message") or "").strip()
    model = normalize_model(payload.get("model"))
    question_payload = public_bank_question(question, include_answer=True)

    if mode == "check":
        task = "检查这道题的题干、选项和参考答案是否一致，特别说明补全显示或AI参考答案是否影响答案来源。"
    elif mode == "ask" and message:
        task = f"回答学生关于这道题的问题：{message}"
    else:
        task = "讲解这道题的知识点、解题步骤、参考答案依据，以及常见错误。"

    messages = [
            {
                "role": "system",
                "content": "你是数据结构课程助教。输出中文 Markdown，可使用表格、公式 $...$、代码块和列表。不要编造与题干无关的内容。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "question": question_payload,
                        "requirements": [
                            "先给结论，再给理由。",
                            "涉及复杂度、矩阵下标、树结点公式时用清晰公式。",
                            "如果题目来自补全表，请说明补全只用于显示，标准答案仍来自题库。",
                            "如果作业题答案来源是AI参考答案，请明确它不是Word官方答案。",
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    return {
        "question": question,
        "messages": messages,
        "model": model,
        "mode": mode,
        "temperature": 0.2 if mode != "check" else 0.0,
    }


def question_ai_assistant(bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = question_ai_request(bank, payload)
    question = request_payload["question"]
    model = request_payload["model"]
    content = call_deepseek(
        request_payload["messages"],
        model=model,
        temperature=request_payload["temperature"],
        json_mode=False,
        max_tokens=1600,
    )
    return {
        "bank_id": bank.bank_id,
        "question_id": question.id,
        "mode": request_payload["mode"],
        "model": model,
        "reply": content,
    }


def question_ai_assistant_stream(bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> Any:
    request_payload = question_ai_request(bank, payload)
    yield from call_ai_stream(
        request_payload["messages"],
        model=request_payload["model"],
        temperature=request_payload["temperature"],
        max_tokens=1600,
    )


# ── 个性化推荐 ──

def recommend_questions(
    bank: QuestionBank | AssignmentBank,
    db: PracticeDatabase,
    profile: dict[str, Any] | None,
    user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    requested_count = int(payload.get("count") or 10)
    qtypes = payload.get("types") or []
    if not qtypes:
        qtypes = ["单选题", "多选题", "填空题", "判断题"]

    # 获取可用题目
    available = [q for q in bank.questions if (not qtypes or q.qtype in qtypes)]
    if not available:
        return {"questions": [], "reason": "没有符合条件的题目。"}

    # 过滤已答过的题（近期）
    with db.connect() as conn:
        recent_ids = {
            row[0]
            for row in conn.execute(
                "SELECT question_id FROM attempts WHERE user_id = ? AND source != 'ai' ORDER BY created_at DESC LIMIT 200",
                (user_id,),
            ).fetchall()
        }

    # 排序：弱项章节优先 + 错题优先
    weak_concepts = set((profile or {}).get("weak_concepts", []))
    type_accuracy = (profile or {}).get("type_accuracy", {})

    def question_score(q: Any) -> float:
        score = 0.0
        # 弱项章节加分
        if q.chapter in weak_concepts:
            score += 3.0
        # 弱项题型加分
        if type_accuracy.get(q.qtype, 1.0) < 0.5:
            score += 2.0
        # 未做过加分
        if q.id not in recent_ids:
            score += 1.0
        # 随机扰动
        score += random.uniform(0, 0.5)
        return score

    sorted_questions = sorted(available, key=question_score, reverse=True)

    # 取前N题 + 随机打乱
    selected = sorted_questions[: min(requested_count * 2, len(sorted_questions))]
    random.shuffle(selected)
    selected = selected[:requested_count]

    return {
        "questions": [public_bank_question(q) for q in selected],
        "count": len(selected),
        "profile_summary": {
            "weak_concepts": list(weak_concepts),
            "type_accuracy": type_accuracy,
        } if profile else {},
    }


# ── 苏格拉底式AI导师 ──

SOCRATIC_SYSTEM_PROMPT = """你是 StructMind 数据结构课程的苏格拉底式AI导师。

## 你的教学理念
你不是答案提供者，而是思维引导者。你的目标是通过提问和引导，让学生自己发现答案，真正理解数据结构的核心概念。

## 核心规则
1. **永远不要直接给出答案**。用反问引导学生思考关键概念。
2. **从学生已有的知识出发**，逐步深入，每次只推进一个层次。
3. **当学生卡住时**，给出提示（hint）而不是答案。提示应该是概念性的，引导学生回忆相关知识点。
4. **鼓励学生用自己的话解释推理过程**。当学生给出推理后，先肯定正确的部分，再指出需要修正的地方。
5. **在学生理解后**，提出一个延伸问题巩固知识。
6. **保持耐心和鼓励**。如果学生多次尝试仍不理解，换一个角度或更简单的例子来解释概念。

## 对话格式
- 先用一句简短的肯定/鼓励开头（如"很好的尝试！"、"你离答案很近了"）
- 然后提出1-2个引导性问题
- 如果需要，给出一个概念提示
- 偶尔总结一下当前的讨论进展

## 输出风格
- 使用 Markdown 格式
- 数据结构和算法概念用 `代码块` 标记
- 复杂公式用 $...$ 表达
- 保持回复简洁，每次不超过3-4个要点
- 使用友好、亲切的语气，就像一位耐心的学长/学姐

## 数据结构教学重点
- 线性表、栈、队列、串
- 树与二叉树（遍历、线索树、哈夫曼树）
- 图（遍历、最小生成树、最短路径、拓扑排序）
- 查找（顺序查找、折半查找、哈希表）
- 排序（插入、交换、选择、归并）
- 算法复杂度分析
"""


def socratic_tutor(
    bank: QuestionBank | AssignmentBank,
    db: PracticeDatabase,
    payload: dict[str, Any],
    user_id: int,
) -> dict[str, Any]:
    model = normalize_model(payload.get("model"))
    message = str(payload.get("message") or "").strip()
    if not message:
        raise ValueError("请输入你的问题或思考。")

    question_id = payload.get("question_id")
    question_context = ""
    if question_id:
        q = bank.by_id.get(int(question_id))
        if q:
            question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

    conversation_id = payload.get("conversation_id")
    history = []
    if conversation_id:
        try:
            convs = db.get_conversations(user_id, 1)
            for conv in convs:
                if conv["id"] == int(conversation_id):
                    history = conv["messages"]
                    break
        except Exception:
            pass

    messages = [
        {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT + question_context},
        *history[-10:],  # 最近10轮对话
        {"role": "user", "content": message},
    ]

    reply = call_deepseek(
        messages,
        model=model,
        temperature=0.7,
        json_mode=False,
        max_tokens=1200,
    )

    # 保存对话
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    if conversation_id:
        with db.connect() as conn:
            conn.execute(
                "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(history, ensure_ascii=False), time.time(), int(conversation_id)),
            )
        new_id = int(conversation_id)
    else:
        new_id = db.save_conversation(user_id, int(question_id) if question_id else None, "tutor", history)

    return {
        "conversation_id": new_id,
        "reply": reply,
        "model": model,
        "mode": "socratic_tutor",
    }


def socratic_tutor_stream(
    bank: QuestionBank | AssignmentBank,
    db: PracticeDatabase,
    payload: dict[str, Any],
    user_id: int,
) -> Any:
    model = normalize_model(payload.get("model"))
    message = str(payload.get("message") or "").strip()
    if not message:
        raise ValueError("请输入你的问题或思考。")

    question_id = payload.get("question_id")
    question_context = ""
    if question_id:
        q = bank.by_id.get(int(question_id))
        if q:
            question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

    conversation_id = payload.get("conversation_id")
    history = []
    if conversation_id:
        try:
            convs = db.get_conversations(user_id, 1)
            for conv in convs:
                if conv["id"] == int(conversation_id):
                    history = conv["messages"]
                    break
        except Exception:
            pass

    messages = [
        {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT + question_context},
        *history[-10:],
        {"role": "user", "content": message},
    ]

    full_reply = ""
    for delta in call_ai_stream(messages, model=model, temperature=0.7, max_tokens=1200):
        full_reply += delta
        yield {"delta": delta}

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": full_reply})
    if conversation_id:
        with db.connect() as conn:
            conn.execute(
                "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(history, ensure_ascii=False), time.time(), int(conversation_id)),
            )
    else:
        db.save_conversation(user_id, int(question_id) if question_id else None, "tutor", history)


# ── 安全：速率限制 ──

RATE_LIMIT_WINDOW = 60  # 60秒窗口
RATE_LIMIT_MAX_REQUESTS = 120  # 每窗口最多120请求
AUTH_RATE_LIMIT_MAX = 10  # 认证接口每窗口最多10请求
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(client_ip: str, endpoint_type: str = "general") -> None:
    now = time.time()
    window = RATE_LIMIT_WINDOW
    max_req = RATE_LIMIT_MAX_REQUESTS if endpoint_type == "general" else AUTH_RATE_LIMIT_MAX
    key = f"{client_ip}:{endpoint_type}"
    timestamps = _rate_limit_store[key]
    # 清理过期记录
    timestamps[:] = [t for t in timestamps if now - t < window]
    if len(timestamps) >= max_req:
        raise PermissionError(f"请求过于频繁，请{window}秒后重试。")
    timestamps.append(now)


# ── 安全：输入验证 ──

def validate_account(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) < 2 or len(value) > 32:
        raise ValueError("账号长度需在2-32个字符之间。")
    if not re.match(r'^[a-zA-Z0-9_@.\-]+$', value):
        raise ValueError("账号只能包含字母、数字、下划线、@、点和短横线。")
    return value


def validate_password(value: str) -> str:
    if not value or len(value) < 8 or len(value) > 128:
        raise ValueError("密码长度需在8-128个字符之间。")
    if not re.search(r'[A-Z]', value):
        raise ValueError("密码必须包含至少一个大写字母。")
    if not re.search(r'[a-z]', value):
        raise ValueError("密码必须包含至少一个小写字母。")
    if not re.search(r'[0-9]', value):
        raise ValueError("密码必须包含至少一个数字。")
    return value


def validate_name(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) < 1 or len(value) > 50:
        raise ValueError("姓名长度需在1-50个字符之间。")
    return value


def validate_phone(value: str) -> str:
    value = (value or "").strip()
    if not re.match(r'^\d{11}$', value):
        raise ValueError("请输入正确的11位手机号码。")
    return value


def validate_question_id(value: Any) -> int:
    try:
        qid = int(value)
        if qid < 1:
            raise ValueError
        return qid
    except (ValueError, TypeError):
        raise ValueError("无效的题目ID。")


class AppHandler(BaseHTTPRequestHandler):
    exam_bank: QuestionBank
    assignment_bank: AssignmentBank
    db: PracticeDatabase

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def query_params(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    def selected_bank(self, bank_id: str | None) -> QuestionBank | AssignmentBank:
        normalized = (bank_id or "exam").strip()
        if normalized in {"exam", "bank"}:
            return self.exam_bank
        if normalized == "assignment":
            return self.assignment_bank
        raise ValueError(f"不支持的题库: {normalized}")

    def do_GET(self) -> None:
        try:
            params = self.query_params()
            bank_id = (params.get("bank_id") or ["exam"])[0]
            path = self.path.split("?")[0]
            if path == "/api/auth/me":
                session = require_auth(self)
                self.send_json({"user": session})
            elif path == "/api/admin/pending":
                require_admin(self)
                self.send_json({"users": self.db.get_pending_users()})
            elif path == "/api/admin/users":
                require_admin(self)
                self.send_json({"users": self.db.get_all_users()})
            elif path == "/api/profile":
                session = require_auth(self)
                profile = self.db.get_user_profile(session["user_id"])
                if not profile:
                    profile = self.db.update_user_profile(session["user_id"])
                self.send_json({"profile": profile, "user": session})
            elif path == "/api/stats":
                self.send_json(stats_payload(self.exam_bank, self.assignment_bank, self.db))
            elif path == "/api/config":
                self.send_json(config_payload())
            elif path == "/api/discussions":
                self.send_json({"discussions": [public_discussion(item) for item in self.exam_bank.discussions]})
            elif path == "/api/questions":
                bank = self.selected_bank(bank_id)
                self.send_json({"bank_id": bank.bank_id, "questions": [public_bank_question(item) for item in bank.questions]})
            elif path == "/api/supplements":
                self.send_json(supplements_payload(self.exam_bank, self.assignment_bank))
            elif path == "/api/wrong":
                try:
                    session = require_auth(self)
                    self.send_json({"items": self.db.wrong_attempts(self.exam_bank)})
                except PermissionError:
                    self.send_json({"items": []})
            elif self.path.startswith("/assets/"):
                self.send_asset()
            elif path == "/api/bank/list":
                session = parse_auth_header(self)
                user_id = session["user_id"] if session else 0
                user_banks = self.db.list_custom_banks(user_id) if user_id > 0 else []
                public_banks = self.db.list_public_banks()
                # 合并去重
                seen = {b["id"] for b in user_banks}
                all_banks = list(user_banks)
                for b in public_banks:
                    if b["id"] not in seen:
                        all_banks.append(b)
                        seen.add(b["id"])
                self.send_json({"banks": all_banks})
            elif path == "/api/learning/plan":
                session = require_auth(self)
                plan = self.db.get_learning_plan(session["user_id"])
                self.send_json({"plan": plan})
            elif path == "/api/community/posts":
                params = self.query_params()
                question_id = int(params["question_id"][0]) if params.get("question_id") else None
                bank_id = params.get("bank_id", [None])[0]
                limit = int(params.get("limit", [50])[0])
                offset = int(params.get("offset", [0])[0])
                posts = self.db.get_posts(question_id=question_id, bank_id=bank_id, limit=limit, offset=offset)
                self.send_json({"posts": posts})
            elif path == "/api/leaderboard":
                params = self.query_params()
                period = params.get("period", ["week"])[0]
                board = self.db.get_leaderboard(period)
                self.send_json({"leaderboard": board, "period": period})
            elif path == "/api/report/pdf":
                session = require_auth(self)
                self.send_learning_report(session)
            else:
                self.serve_static()
        except Exception as exc:
            self.send_error_json(exc)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            path = self.path.split("?")[0]
            if path == "/api/auth/register":
                check_rate_limit(self.client_address[0], "auth")
                account = validate_account(payload.get("account", ""))
                password = validate_password(payload.get("password", ""))
                name = validate_name(payload.get("name", ""))
                phone = validate_phone(payload.get("phone", ""))
                self.send_json(self.db.create_user(account, password, name, phone))
            elif path == "/api/auth/login":
                check_rate_limit(self.client_address[0], "auth")
                account = validate_account(payload.get("account", ""))
                password = payload.get("password", "")
                if not password:
                    raise ValueError("密码不能为空。")
                client_ip = self.client_address[0]
                user = self.db.authenticate(account, password, client_ip)
                if not user:
                    raise ValueError("账号或密码错误。")
                if user["status"] == "pending":
                    raise ValueError("账号正在等待管理员审批，请耐心等候。")
                if user["status"] == "rejected":
                    raise ValueError("账号注册已被拒绝。")
                token = self.db.create_session(user["id"])
                self.send_json({"token": token, "user": user})
            elif path == "/api/auth/logout":
                auth_header = self.headers.get("Authorization") or ""
                if auth_header.startswith("Bearer "):
                    self.db.delete_session(auth_header[7:].strip())
                self.send_json({"ok": True})
            elif path == "/api/admin/approve":
                require_admin(self)
                user_id = int(payload["user_id"])
                approved = bool(payload.get("approved", True))
                self.send_json({"user": self.db.approve_user(user_id, approved)})
            elif path == "/api/recommend/questions":
                session = require_auth(self)
                profile = self.db.get_user_profile(session["user_id"])
                bank = self.selected_bank(payload.get("bank_id", "exam"))
                self.send_json(recommend_questions(bank, self.db, profile, session["user_id"], payload))
            elif path == "/api/ai/tutor":
                session = require_auth(self)
                self.send_json(socratic_tutor(self.exam_bank, self.db, payload, session["user_id"]))
            elif path == "/api/ai/tutor/stream":
                session = require_auth(self)
                self.send_socratic_stream(payload, session["user_id"])
            elif path == "/api/session":
                bank_id = payload.get("bank_id")
                # 尝试自定义题库
                custom_bank_id = None
                try:
                    custom_bank_id = int(bank_id) if bank_id and str(bank_id).isdigit() else None
                except (ValueError, TypeError):
                    pass
                if custom_bank_id:
                    custom_bank = self.db.get_custom_bank(custom_bank_id)
                    if custom_bank:
                        questions_data = json.loads(custom_bank["questions_json"])
                        session_data = {
                            "session_id": str(uuid.uuid4()),
                            "bank_id": f"custom_{custom_bank_id}",
                            "mode": payload.get("mode", "sequence"),
                            "total_available": len(questions_data),
                            "count": len(questions_data),
                            "questions": questions_data,
                        }
                        self.send_json(session_data)
                    else:
                        raise KeyError("自定义题库不存在。")
                else:
                    bank = self.selected_bank(bank_id)
                    self.send_json(create_session(bank, payload))
            elif path == "/api/config":
                self.send_json(update_runtime_config(payload))
            elif path == "/api/answer":
                question_id = int(payload.get("question_id"))
                bank = self.selected_bank(payload.get("bank_id"))
                question = bank.by_id.get(question_id)
                if not question:
                    raise KeyError("题目不存在。")
                if isinstance(question, AssignmentQuestion) and question.qtype == "简答题":
                    raise ValueError("简答作业题请使用 AI 参考批改。")
                result = grade_answer(question, payload.get("answer"))
                user_id = 0
                try:
                    session = parse_auth_header(self)
                    if session:
                        user_id = session["user_id"]
                except Exception:
                    pass
                self.db.record_attempt(
                    question.id,
                    bank.bank_id,
                    question.qtype,
                    payload.get("answer"),
                    question.answer,
                    result["is_correct"],
                    user_id=user_id,
                )
                result["question"] = public_bank_question(question, include_answer=True)
                # 更新用户画像
                if user_id > 0:
                    try:
                        profile = self.db.update_user_profile(user_id)
                        result["profile"] = profile
                    except Exception:
                        pass
                self.send_json(result)
            elif path == "/api/ai/generate":
                session = parse_auth_header(self)
                user_id = session["user_id"] if session else 0
                result = generate_ai_question(self.exam_bank, self.db, {**payload, "user_id": user_id})
                self.send_json(result)
            elif path == "/api/ai/answer":
                self.send_json(grade_ai_answer(self.db, payload))
            elif path == "/api/ai/supplement":
                self.send_json(ai_supplement_question(self.exam_bank, payload))
            elif path == "/api/question/ai":
                bank = self.selected_bank(payload.get("bank_id"))
                self.send_json(question_ai_assistant(bank, payload))
            elif path == "/api/question/ai/stream":
                bank = self.selected_bank(payload.get("bank_id"))
                self.send_question_ai_stream(bank, payload)
            elif path == "/api/assignment/grade":
                self.send_json(grade_assignment(self.assignment_bank, self.db, payload))
            elif path == "/api/discussion/grade":
                self.send_json(grade_discussion(self.exam_bank, self.db, payload))
            elif path == "/api/bank/upload":
                session = require_auth(self)
                name = str(payload.get("name") or "").strip()
                if not name or len(name) > 100:
                    raise ValueError("题库名称长度需在1-100个字符之间。")
                questions = payload.get("questions") or []
                if not isinstance(questions, list):
                    raise ValueError("questions 必须是数组。")
                bank_id = self.db.create_custom_bank(
                    name, session["user_id"],
                    json.dumps(questions, ensure_ascii=False),
                )
                self.send_json({"bank_id": bank_id, "name": name})
            elif path == "/api/bank/get":
                bank_id = int(payload.get("bank_id") or 0)
                bank = self.db.get_custom_bank(bank_id)
                if not bank:
                    raise KeyError("题库不存在。")
                self.send_json({"bank": bank})
            elif path == "/api/learning/generate-plan":
                session = require_auth(self)
                plan_data = generate_learning_plan_data(self.exam_bank, self.db, session["user_id"])
                plan_id = self.db.create_learning_plan(session["user_id"], plan_data)
                plan = self.db.get_learning_plan(session["user_id"])
                self.send_json({"plan": plan})
            elif path == "/api/community/post":
                session = require_auth(self)
                title = str(payload.get("title") or "").strip()
                content = str(payload.get("content") or "").strip()
                if not title or not content:
                    raise ValueError("标题和内容不能为空。")
                question_id = payload.get("question_id")
                bank_id = payload.get("bank_id")
                post_id = self.db.create_post(
                    session["user_id"],
                    int(question_id) if question_id else None,
                    str(bank_id) if bank_id else None,
                    title, content,
                )
                self.send_json({"post_id": post_id})
            elif path == "/api/community/reply":
                session = require_auth(self)
                post_id = int(payload.get("post_id") or 0)
                content = str(payload.get("content") or "").strip()
                if not content:
                    raise ValueError("回复内容不能为空。")
                reply_id = self.db.create_reply(post_id, session["user_id"], content)
                self.send_json({"reply_id": reply_id})
            else:
                self.send_json({"error": "接口不存在。"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_error_json(exc)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _set_security_headers(self) -> None:
        """设置安全响应头"""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        # CORS 头
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求"""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_security_headers()
        self.end_headers()

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._set_security_headers()
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, exc: Exception) -> None:
        status = HTTPStatus.BAD_REQUEST
        if isinstance(exc, AIProviderError):
            status = HTTPStatus.BAD_GATEWAY
        elif isinstance(exc, KeyError):
            status = HTTPStatus.NOT_FOUND
        elif isinstance(exc, ValueError):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, PermissionError):
            status = HTTPStatus.FORBIDDEN
        self.send_json({"error": str(exc)}, status=status)

    def send_sse(self, payload: dict[str, Any]) -> None:
        data = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(data)
        self.wfile.flush()

    def send_question_ai_stream(self, bank: QuestionBank | AssignmentBank, payload: dict[str, Any]) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self._set_security_headers()
        self.end_headers()
        try:
            for delta in question_ai_assistant_stream(bank, payload):
                self.send_sse({"delta": delta})
            self.send_sse({"done": True})
        except Exception as exc:
            self.send_sse({"error": str(exc), "done": True})
        finally:
            self.close_connection = True

    def send_socratic_stream(self, payload: dict[str, Any], user_id: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        bank = self.selected_bank(payload.get("bank_id"))
        try:
            for event in socratic_tutor_stream(bank, self.db, payload, user_id):
                self.send_sse(event)
            self.send_sse({"done": True})
        except Exception as exc:
            self.send_sse({"error": str(exc), "done": True})
        finally:
            self.close_connection = True

    def send_learning_report(self, session: dict[str, Any]) -> None:
        """生成并返回HTML学习报告"""
        report_data = self.db.get_learning_report_data(session["user_id"])
        stats = report_data["stats"]
        user_info = report_data["user"]

        # 构建HTML报告
        type_accuracy_rows = ""
        for t, d in report_data.get("type_accuracy", {}).items():
            type_accuracy_rows += f"""
                <tr>
                    <td>{t}</td>
                    <td>{d['correct']}</td>
                    <td>{d['total']}</td>
                    <td>{int(d['accuracy'] * 100)}%</td>
                </tr>"""

        recent_rows = ""
        for r in report_data.get("recent_practice", [])[:10]:
            status = "正确" if r["is_correct"] else "错误"
            status_color = "#2e7d32" if r["is_correct"] else "#c62828"
            recent_rows += f"""
                <tr>
                    <td>题{r['question_id']}</td>
                    <td>{r['qtype']}</td>
                    <td style="color:{status_color}">{status}</td>
                    <td>{time.strftime('%m-%d %H:%M', time.localtime(r['created_at']))}</td>
                </tr>"""

        weak_items = "".join(f"<li>{w}</li>" for w in report_data.get("weak_concepts", []))
        strong_items = "".join(f"<li>{s}</li>" for s in report_data.get("strong_concepts", []))

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>学习报告 - {user_info['name']}</title>
<style>
    @media print {{
        body {{ margin: 0; padding: 20px; }}
        .no-print {{ display: none !important; }}
        @page {{ size: A4; margin: 20mm; }}
    }}
    body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
    h1 {{ text-align: center; color: #1565c0; border-bottom: 2px solid #1565c0; padding-bottom: 10px; }}
    h2 {{ color: #1976d2; margin-top: 30px; }}
    .meta {{ text-align: center; color: #666; margin-bottom: 30px; }}
    .stats-grid {{ display: flex; gap: 20px; margin-bottom: 30px; }}
    .stat-card {{ flex: 1; text-align: center; padding: 20px; border-radius: 8px; background: #e3f2fd; }}
    .stat-card .value {{ font-size: 28px; font-weight: bold; color: #1565c0; }}
    .stat-card .label {{ font-size: 14px; color: #666; margin-top: 5px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 10px; text-align: center; }}
    th {{ background: #e3f2fd; color: #1565c0; }}
    tr:nth-child(even) {{ background: #f5f5f5; }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 5px 0; }}
    .recommendations {{ background: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin: 20px 0; }}
    .print-btn {{ display: block; margin: 20px auto; padding: 10px 30px; font-size: 16px; background: #1565c0; color: white; border: none; border-radius: 5px; cursor: pointer; }}
    .print-btn:hover {{ background: #0d47a1; }}
</style>
</head>
<body>
<h1>StructMind 学习报告</h1>
<div class="meta">
    <p>姓名：{user_info['name']}（{user_info['account']}）</p>
    <p>报告生成时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}</p>
</div>

<h2>练习统计</h2>
<div class="stats-grid">
    <div class="stat-card">
        <div class="value">{stats['total_attempts']}</div>
        <div class="label">总练习次数</div>
    </div>
    <div class="stat-card">
        <div class="value">{stats['total_correct']}</div>
        <div class="label">答对次数</div>
    </div>
    <div class="stat-card">
        <div class="value">{int(stats['overall_accuracy'] * 100)}%</div>
        <div class="label">总正确率</div>
    </div>
</div>

<h2>题型正确率</h2>
<table>
    <tr><th>题型</th><th>正确数</th><th>总次数</th><th>正确率</th></tr>
    {type_accuracy_rows if type_accuracy_rows else '<tr><td colspan="4">暂无数据</td></tr>'}
</table>

<h2>近期练习记录</h2>
<table>
    <tr><th>题目</th><th>题型</th><th>结果</th><th>时间</th></tr>
    {recent_rows if recent_rows else '<tr><td colspan="4">暂无练习记录</td></tr>'}
</table>

<h2>弱项分析</h2>
{'<ul>' + weak_items + '</ul>' if weak_items else '<p>暂无明确弱项，继续保持！</p>'}

<h2>强项</h2>
{'<ul>' + strong_items + '</ul>' if strong_items else '<p>继续多练习以积累强项。</p>'}

<div class="recommendations">
    <h3>学习建议</h3>
    <ul>
        <li>针对弱项章节反复练习对应题型</li>
        <li>每天保持至少20题练习量</li>
        <li>善用AI讲解功能理解错题</li>
        <li>定期使用苏格拉底式导师深入理解概念</li>
    </ul>
</div>

<button class="print-btn no-print" onclick="window.print()">打印报告 / 保存为PDF</button>

</body>
</html>"""
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._set_security_headers()
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self) -> None:
        request_path = self.path.split("?", 1)[0]
        if request_path in {"", "/"}:
            file_path = STATIC_DIR / "index.html"
        else:
            # 防护路径遍历
            clean = request_path.lstrip("/")
            if ".." in clean or clean.startswith("/"):
                self.send_response(HTTPStatus.FORBIDDEN)
                self.end_headers()
                return
            file_path = STATIC_DIR / clean
            # 确保解析后仍在 STATIC_DIR 内
            try:
                resolved = file_path.resolve()
                if not str(resolved).startswith(str(STATIC_DIR.resolve())):
                    self.send_response(HTTPStatus.FORBIDDEN)
                    self.end_headers()
                    return
                file_path = resolved
            except (ValueError, OSError):
                file_path = STATIC_DIR / "index.html"
        if not file_path.exists() or not file_path.is_file():
            file_path = STATIC_DIR / "index.html"
        self.send_file(file_path)

    def send_asset(self) -> None:
        request_path = unquote(urlparse(self.path).path)
        relative = Path(request_path.removeprefix("/assets/"))
        # 严格的路径遍历防护
        if relative.is_absolute() or ".." in relative.parts:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        # 解析真实路径，确保在允许的目录内
        real_path = (ASSET_DIR / relative).resolve()
        if not str(real_path).startswith(str(ASSET_DIR.resolve())):
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        self.send_file(real_path)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._set_security_headers()
        if path.suffix.lower() in {".html", ".js", ".css"}:
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, stored_hash = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
        return dk.hex() == stored_hash
    except (ValueError, AttributeError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


ADMIN_ACCOUNT = os.environ.get("SM_ADMIN_ACCOUNT", "tanshuhong")
ADMIN_PASSWORD = os.environ.get("SM_ADMIN_PASSWORD", "XX05020604")


def parse_auth_header(handler: "AppHandler") -> dict[str, Any] | None:
    auth = handler.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        return handler.db.get_session(token)
    return None


def require_admin(handler: "AppHandler") -> dict[str, Any]:
    session = parse_auth_header(handler)
    if not session:
        raise PermissionError("请先登录。")
    if session.get("role") != "admin":
        raise PermissionError("仅管理员可执行此操作。")
    return session


def require_auth(handler: "AppHandler") -> dict[str, Any]:
    session = parse_auth_header(handler)
    if not session:
        raise PermissionError("请先登录。")
    if session.get("status") == "pending":
        raise PermissionError("账号尚未通过审批，请等待管理员审核。")
    if session.get("status") == "rejected":
        raise PermissionError("账号注册已被拒绝。")
    return session


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    exam_bank = load_question_bank()
    assignment_bank = load_assignment_bank()
    db = PracticeDatabase(DB_PATH)
    # 初始化管理员账号
    try:
        admin = db.authenticate(ADMIN_ACCOUNT, ADMIN_PASSWORD)
        if admin:
            print(f"管理员账号已就绪: {ADMIN_ACCOUNT}")
    except Exception:
        pass
    try:
        db.create_user(ADMIN_ACCOUNT, ADMIN_PASSWORD, "谭书宏", "13800000000")
        print(f"已创建管理员账号: {ADMIN_ACCOUNT}")
    except ValueError:
        pass  # 已存在

    AppHandler.exam_bank = exam_bank
    AppHandler.assignment_bank = assignment_bank
    AppHandler.db = db
    server = ThreadingHTTPServer((host, port), AppHandler)

    # HTTPS 支持：通过环境变量配置 SSL 证书和密钥
    ssl_cert = os.environ.get("SM_SSL_CERT")
    ssl_key = os.environ.get("SM_SSL_KEY")
    if ssl_cert and ssl_key:
        if os.path.isfile(ssl_cert) and os.path.isfile(ssl_key):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(ssl_cert, ssl_key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            protocol = "https"
        else:
            print(f"SSL证书或密钥文件不存在，将使用HTTP模式。")
            protocol = "http"
    else:
        protocol = "http"

    print(f"题库载入完成: {len(exam_bank.questions)} 道考试客观题, "
          f"{len(exam_bank.discussions)} 道讨论题, {len(assignment_bank.questions)} 道作业题")
    print(f"StructMind 服务地址: {protocol}://{host}:{port}")
    print(f"管理员账号: {ADMIN_ACCOUNT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
