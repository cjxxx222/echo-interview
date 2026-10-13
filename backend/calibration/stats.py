"""校准统计 —— 全部纯 Python，不依赖 scipy，且只使用可手工验证正确性的指标。

指标口径（对外叙事时就用这套说法，别自己加戏）：
1. 人-人基线（天花板）：所有真人评委两两 Spearman ρ 的均值 + bootstrap 95% CI
2. AI-人一致性：每个维度，AI 分 vs 人类均分 的 Spearman ρ + bootstrap 95% CI
3. 同向率：AI 与人类均分同处量表上半区/下半区的比例
4. 核心比值：AI-人 ρ ÷ 人-人 ρ = 「AI 达到人类一致性的 XX%」——比裸报 ρ 抗追问

为什么不实现 ICC / Krippendorff α：公式变体多，当期实现无法用已知样例验证数值正确性。
宁可指标少而每个都对——这是公开资产，错一个数比少一个指标致命得多。
样本小（n≈40）时所有指标的 CI 都宽，对外一律报区间，不裸报点估计。
"""

import random
from itertools import combinations


def _rank(values: list) -> list:
    """平均秩（ties 取平均），用于 Spearman 的 tie 修正。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based 平均秩
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: list, y: list) -> float:
    """Spearman 秩相关（tie 修正版）。数据点不足或零方差时返回 nan。"""
    if len(x) != len(y) or len(x) < 3:
        return float("nan")
    rx, ry = _rank(x), _rank(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / (vx * vy) ** 0.5


def _bootstrap_ci(fn, data: list, iterations: int = 2000, alpha: float = 0.05) -> tuple:
    """对 data 有放回重采样，返回 fn 的百分位 CI。data 为空返回 (nan, nan)。"""
    if len(data) < 3:
        return (float("nan"), float("nan"))
    rng = random.Random(42)  # 固定种子：结果可复现
    vals = []
    n = len(data)
    for _ in range(iterations):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        v = fn(sample)
        if v == v:  # 过滤 nan
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int(alpha / 2 * len(vals))]
    hi = vals[int((1 - alpha / 2) * len(vals)) - 1]
    return (lo, hi)


def mean_pairwise_spearman(rater_vectors: list[list]) -> float:
    """人-人基线：所有真人评委两两 ρ 的均值（评委各自的维度分向量）。"""
    rhos = [
        spearman(a, b) for a, b in combinations(rater_vectors, 2)
    ]
    rhos = [r for r in rhos if r == r]
    return sum(rhos) / len(rhos) if rhos else float("nan")


def direction_rate(ai: list, human_mean: list, ai_threshold: float, human_threshold: float) -> float:
    """同向率：两侧分数同处量表上半区/下半区的比例。"""
    if not ai:
        return float("nan")
    same = sum(
        1 for a, h in zip(ai, human_mean)
        if (a - ai_threshold) * (h - human_threshold) > 0
    )
    return same / len(ai)


def badcase_matrix(packets: list[dict], dimension: str,
                   ai_threshold: float = 50.0, human_threshold: float = 3.0) -> list[dict]:
    """AI 系统偏严/偏松分析：按人类均分把评测包分桶，报告每桶的 AI-人 平均残差。

    残差 = AI 分（归一化到 0-100）− 人类均分（归一化到 0-100）。
    残差持续为正 = AI 在该水平段系统性偏松。
    """
    buckets: dict[str, list[float]] = {}

    def _bucket(h: float) -> str:
        if h <= human_threshold:
            return "低分区(≤3)"
        if h >= 4:
            return "高分区(≥4)"
        return "中分区"

    for p in packets:
        h = p.get("human_means", {}).get(dimension)
        a = p.get("ai_scores", {}).get(dimension)
        if h is None or a is None:
            continue
        h100 = (h - 1) / 4 * 100        # 1-5 → 0-100
        buckets.setdefault(_bucket(h), []).append(a - h100)

    return [
        {"bucket": b, "count": len(v),
         "mean_residual": round(sum(v) / len(v), 1),
         "interpretation": "AI 偏松" if sum(v) / len(v) > 5 else ("AI 偏严" if sum(v) / len(v) < -5 else "基本无偏")}
        for b, v in sorted(buckets.items())
    ]


def _clean_nan(obj):
    """递归把 nan 换成 None——响应里绝不出现 nan（JSON 不允许，会 500）。"""
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def compute_calibration(packets: list[dict], dimensions: list[str]) -> dict:
    """校准实验主入口。

    packets: [{
        "ai_scores": {dim: 0-100},
        "human_means": {dim: 1-5 均分},
        "rater_vectors": {reviewer_id: {dim: 1-5}}  # 各评委原始分
    }]
    """
    if len(packets) < 3:
        return {"error": f"评测包数量 {len(packets)} 不足 3，样本太小不予统计", "packets": len(packets)}

    result = {}

    # 人-人基线：每个维度下，各评委的分向量两两 ρ 均值
    human_baselines = {}
    for dim in dimensions:
        vectors = [
            [pr["rater_vectors"][rid][dim] for pr in packets if rid in pr["rater_vectors"]]
            for rid in _all_raters(packets)
        ]
        vectors = [v for v in vectors if len(v) >= 3]
        human_baselines[dim] = mean_pairwise_spearman(vectors) if len(vectors) >= 2 else float("nan")
    result["human_baseline_rho"] = human_baselines

    per_dim = {}
    for dim in dimensions:
        ai = [p["ai_scores"][dim] for p in packets if dim in p.get("ai_scores", {})]
        hm = [p["human_means"][dim] for p in packets if dim in p.get("human_means", {})]
        n = min(len(ai), len(hm))
        ai, hm = ai[:n], hm[:n]

        if n < 3:
            per_dim[dim] = {"n": n, "note": "样本不足 3，无法计算相关"}
            continue

        # 零方差：AI 或人类均分在该维度恒定 → 秩相关无定义。
        # 小样本评测集里很常见，输出说明而不是 nan（nan 会让 JSON 序列化直接失败）。
        if len(set(ai)) < 2 or len(set(hm)) < 2:
            per_dim[dim] = {
                "n": n,
                "note": "该维度分数无变异（AI 或人类均分恒定），无法计算秩相关——这本身是要在报告里说明的现象",
                "direction_rate": round(direction_rate(ai, hm, 50.0, 3.0), 3),
                "badcase_matrix": badcase_matrix(
                    [{"ai_scores": p["ai_scores"], "human_means": p["human_means"]} for p in packets], dim
                ),
            }
            continue

        rho = spearman(ai, hm)
        lo, hi = _bootstrap_ci(lambda s: spearman([x[0] for x in s], [x[1] for x in s]), list(zip(ai, hm)))
        per_dim[dim] = {
            "n": n,
            "spearman_rho": round(rho, 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "direction_rate": round(direction_rate(ai, hm, 50.0, 3.0), 3),
            "human_baseline_rho": round(human_baselines[dim], 3) if human_baselines[dim] == human_baselines[dim] else None,
            "agreement_vs_human": (
                round(rho / human_baselines[dim], 3)
                if human_baselines[dim] and human_baselines[dim] == human_baselines[dim] and human_baselines[dim] != 0
                else None
            ),
            "badcase_matrix": badcase_matrix(
                [{"ai_scores": p["ai_scores"], "human_means": p["human_means"]} for p in packets], dim
            ),
        }
    result["per_dimension"] = per_dim

    valid = [v["spearman_rho"] for v in per_dim.values() if isinstance(v.get("spearman_rho"), float)]
    valid = [v for v in valid if v == v]
    baseline_valid = [b for b in human_baselines.values() if b == b]
    if valid and baseline_valid:
        result["overall"] = {
            "ai_human_rho_mean": round(sum(valid) / len(valid), 3),
            "human_rho_mean": round(sum(baseline_valid) / len(baseline_valid), 3),
            "headline": f"AI 评分达到人类一致性的 {round(100 * (sum(valid)/len(valid)) / (sum(baseline_valid)/len(baseline_valid)))}%",
        }
    else:
        result["overall"] = {
            "note": "没有任何维度同时具备 AI 与人类的有效评分变异，无法给出总体一致性",
            "ai_human_rho_mean": None,
            "human_rho_mean": None,
        }
    return _clean_nan(result)


def _all_raters(packets: list[dict]) -> list[str]:
    seen = []
    for p in packets:
        for rid in p.get("rater_vectors", {}):
            if rid not in seen:
                seen.append(rid)
    return seen
