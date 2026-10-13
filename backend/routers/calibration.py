"""校准实验 API —— 真人盲评的导出、提交、揭晓与统计。

流程：export（导盲评包）→ 真人填表单（看不到 AI 分）→ reveal（揭晓 AI 分）→ stats（一致性计算）。
表单页 /form/{packet_id} 是自包含 HTML，不依赖前端构建，发链接给评委即可用。
"""
import time
import uuid
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from models.schemas import BlindReviewSubmission, DimensionJudgment, ReviewerInfo
from calibration.export import to_blind_packet, ai_dimension_scores
from calibration.rubric import RUBRIC
from calibration.stats import compute_calibration
from dimensions import DIMENSION_KEYS, DIMENSION_LABELS

router = APIRouter()

# 内存存储：packet_id -> blind packet dict（与面试会话一致，重启即清）
_packets: dict[str, dict] = {}


def _get_sessions() -> dict:
    import main
    return main.interview_sessions


class ReviewBody(BaseModel):
    reviewer_id: str
    reviewer_name: str = ""
    judgments: list[dict]   # [{"dimension": "depth", "score": 4, "note": ""}]


@router.post("/export/{interview_id}")
async def export_packet(interview_id: str):
    """把一场已完成的面试导出为盲评包（不含 AI 分）。"""
    session = _get_sessions().get(interview_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")
    if not session.get("evaluations"):
        raise HTTPException(400, "该面试没有任何评估记录，无法导出")

    packet_id = f"bp_{uuid.uuid4().hex[:8]}"
    packet = to_blind_packet(session, packet_id)
    _packets[packet_id] = packet
    return {"packet_id": packet_id, "qa_count": len(packet["qa"]),
            "form_url": f"/api/calibration/form/{packet_id}"}


@router.get("/packets")
async def list_packets():
    return [
        {
            "packet_id": p["packet_id"],
            "target_position": p["target_position"],
            "qa_count": len(p["qa"]),
            "review_count": len(p["reviews"]),
            "revealed": p["revealed"],
        }
        for p in _packets.values()
    ]


@router.post("/{packet_id}/review")
async def submit_review(packet_id: str, body: ReviewBody):
    """提交一份真人盲评。同一 reviewer 对同一 packet 重复提交会覆盖旧提交。"""
    packet = _packets.get(packet_id)
    if not packet:
        raise HTTPException(404, "盲评包不存在")

    judgments = []
    for j in body.judgments:
        dim = j.get("dimension", "")
        if dim not in DIMENSION_KEYS:
            continue
        score = int(j.get("score", 0))
        if not 1 <= score <= 5:
            raise HTTPException(400, f"维度 {dim} 的分数必须在 1-5 之间")
        judgments.append(DimensionJudgment(dimension=dim, score=score, note=j.get("note", "")))

    submission = BlindReviewSubmission(
        reviewer=ReviewerInfo(reviewer_id=body.reviewer_id, name=body.reviewer_name),
        judgments=judgments,
        submitted_at=time.time(),
    )
    packet["reviews"] = [r for r in packet["reviews"] if r.reviewer.reviewer_id != body.reviewer_id]
    packet["reviews"].append(submission)
    return {"ok": True, "reviews_so_far": len(packet["reviews"])}


@router.post("/{packet_id}/reveal")
async def reveal(packet_id: str):
    """盲评结束后揭晓 AI 分（揭晓前评委在任何界面都看不到 AI 分）。"""
    packet = _packets.get(packet_id)
    if not packet:
        raise HTTPException(404, "盲评包不存在")
    session = _get_sessions().get(packet["interview_id"])
    if not session:
        raise HTTPException(409, "源会话已过期，无法揭晓")
    packet["ai_scores"] = ai_dimension_scores(session)
    packet["revealed"] = True
    return {"revealed": True, "ai_scores": packet["ai_scores"]}


@router.get("/stats")
async def stats():
    """一致性统计。只统计已揭晓的评测包；每个维度的评分类目都注明样本量。"""
    packets = []
    for p in _packets.values():
        if not p.get("revealed") or not p["reviews"]:
            continue
        rater_vectors, scores = {}, []
        for r in p["reviews"]:
            rater_vectors[r.reviewer.reviewer_id] = {
                j.dimension: j.score for j in r.judgments
            }
            scores.append((r.reviewer.reviewer_id, r.judgments))
        human_means = {}
        for dim in DIMENSION_KEYS:
            vals = [j.score for _, js in scores for j in js if j.dimension == dim]
            human_means[dim] = sum(vals) / len(vals) if vals else None
        if any(v is None for v in human_means.values()):
            continue
        packets.append({
            "ai_scores": p["ai_scores"],
            "human_means": human_means,
            "rater_vectors": rater_vectors,
        })

    if len(packets) < 3:
        return {"error": f"已揭晓评测包 {len(packets)} 个，不足 3，样本太小不予统计", "packets": len(packets)}
    return compute_calibration(packets, DIMENSION_KEYS)

# =================== 盲评表单页（自包含 HTML，评委免登录） ===================
FORM_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>面试盲评 - {packet_id}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 760px; margin: 0 auto; padding: 24px 16px; background: #f7f7f5; color: #1f1e1c; }}
  h1 {{ font-size: 20px; }}
  .card {{ background: #fff; border: 1px solid #e4e2dc; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }}
  .q {{ font-weight: 600; margin-bottom: 8px; }}
  .a {{ white-space: pre-wrap; color: #444; font-size: 14px; line-height: 1.7; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
  th, td {{ border-bottom: 1px solid #eee; padding: 10px 8px; text-align: left; font-size: 14px; vertical-align: top; }}
  th {{ color: #666; font-weight: 500; }}
  select {{ padding: 6px 10px; border-radius: 8px; border: 1px solid #ccc; font-size: 14px; }}
  button {{ margin-top: 20px; padding: 12px 32px; font-size: 15px; border: none; border-radius: 10px;
           background: #534ab7; color: #fff; cursor: pointer; }}
  .hint {{ font-size: 12px; color: #888; line-height: 1.6; }}
  .banner {{ background: #faecе7; }}
</style>
</head>
<body>
<h1>面试盲评表</h1>
<div class="card" style="background:#fdf6ec;border-color:#f0d9a8">
  <b>盲评须知</b>：请依据下方的问答记录独立打分。<b>本页面不包含任何 AI 评分</b>——
  这是校准实验，你的分数将与 AI 评分做一致性比对。请按量表中的行为描述打分，不要互相讨论。
</div>
<div class="card">
  <label>评委 ID：<input id="rid" style="padding:6px 10px;border-radius:8px;border:1px solid #ccc" placeholder="如 rater1"></label>
  <label style="margin-left:16px">姓名（可选）：<input id="rname" style="padding:6px 10px;border-radius:8px;border:1px solid #ccc"></label>
</div>
{qa_cards}
<div class="card">
  <table>
    <tr><th>维度</th><th>分数（1-5）</th><th>备注（可选）</th></tr>
    {dim_rows}
  </table>
  <button onclick="submit()">提交盲评</button>
  <div id="msg" style="margin-top:12px;font-size:14px"></div>
</div>
<script>
const PACKET_ID = "{packet_id}";
async function submit() {{
  const rid = document.getElementById('rid').value.trim();
  if (!rid) {{ alert('请填写评委 ID'); return; }}
  const judgments = [];
  document.querySelectorAll('select[data-dim]').forEach(sel => {{
    judgments.push({{dimension: sel.dataset.dim, score: parseInt(sel.value), note: ''}});
  }});
  const res = await fetch(`/api/calibration/${{PACKET_ID}}/review`, {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{reviewer_id: rid, reviewer_name: document.getElementById('rname').value, judgments}})
  }});
  const data = await res.json();
  document.getElementById('msg').textContent = res.ok ? `提交成功，本包已有 ${{data.reviews_so_far}} 份盲评` : ('提交失败：' + JSON.stringify(data));
}}
</script>
</body>
</html>"""


def _render_form(packet: dict) -> str:
    qa_cards = "\n".join(
        f'<div class="card"><div class="q">Q{i+1}. {p["question"]}</div><div class="a">{_esc(p["answer"])}</div></div>'
        for i, p in enumerate(packet["qa"])
    )
    dim_rows = "\n".join(
        f'<tr><td><b>{DIMENSION_LABELS[d]}</b><div class="hint">{_esc(RUBRIC[d][3])}｜{_esc(RUBRIC[d][5])}</div></td>'
        f'<td><select data-dim="{d}">{"".join(f"<option value={s}>{s}</option>" for s in range(1, 6))}</select></td>'
        f'<td></td></tr>'
        for d in DIMENSION_KEYS
    )
    return FORM_HTML.replace("{packet_id}", packet["packet_id"]).replace("{qa_cards}", qa_cards).replace("{dim_rows}", dim_rows)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@router.get("/form/{packet_id}", response_class=HTMLResponse)
async def blind_form(packet_id: str):
    packet = _packets.get(packet_id)
    if not packet:
        raise HTTPException(404, "盲评包不存在")
    return _render_form(packet)
