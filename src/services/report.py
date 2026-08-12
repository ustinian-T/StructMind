"""HTML 学习报告生成。"""

from __future__ import annotations

import time
from typing import Any


def generate_learning_report_html(report_data: dict[str, Any]) -> str:
    """生成 HTML 格式的学习报告（保持与原 server.py 一致）。"""
    stats = report_data["stats"]
    user_info = report_data["user"]

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

    return f"""<!DOCTYPE html>
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
