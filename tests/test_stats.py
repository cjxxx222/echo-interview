"""统计函数测试：所有期望值均为手工可验证的已知结果。"""
import math

from calibration.stats import (
    spearman, mean_pairwise_spearman, direction_rate,
    badcase_matrix, compute_calibration,
)
from dimensions import DIMENSION_KEYS


class TestSpearman:
    def test_perfect_positive(self):
        assert spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0

    def test_perfect_negative(self):
        assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == -1.0

    def test_hand_computed_with_ties(self):
        # 手算：x=[1,2,3,4,5] 秩 1..5；y=[1,3,2,4,5] 秩 1,3,2,4,5 → d² 和=2
        # ρ = 1 - 6*2/(5*(25-1)) = 0.9
        assert abs(spearman([1, 2, 3, 4, 5], [1, 3, 2, 4, 5]) - 0.9) < 1e-9

    def test_tied_values(self):
        # 全部并列 → 零方差 → nan
        assert math.isnan(spearman([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_too_few_points(self):
        assert math.isnan(spearman([1, 2], [2, 1]))


class TestDirectionRate:
    def test_all_same_direction(self):
        assert direction_rate([80, 30, 90], [4, 1, 5], 50, 3) == 1.0

    def test_opposite_direction_counts_as_disagree(self):
        assert direction_rate([80, 30], [1, 4], 50, 3) == 0.0

    def test_on_threshold_not_counted(self):
        # 恰好卡在阈值上（乘积为 0）不计入同向
        assert direction_rate([50, 70], [3, 4], 50, 3) == 0.5


class TestMeanPairwiseSpearman:
    def test_perfect_agreement(self):
        v = [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]
        assert mean_pairwise_spearman(v) == 1.0


class TestBadcaseMatrix:
    def test_residual_sign_and_buckets(self):
        packets = [
            {"ai_scores": {"depth": 80}, "human_means": {"depth": 1.5}},  # 人低分 AI高分 → 偏松
            {"ai_scores": {"depth": 75}, "human_means": {"depth": 2.0}},
            {"ai_scores": {"depth": 90}, "human_means": {"depth": 4.5}},  # 人高分 AI高分 → 基本无偏
        ]
        rows = {r["bucket"]: r for r in badcase_matrix(packets, "depth")}
        assert "低分区(≤3)" in rows
        assert rows["低分区(≤3)"]["mean_residual"] > 0
        assert rows["低分区(≤3)"]["interpretation"] == "AI 偏松"
        assert rows["高分区(≥4)"]["mean_residual"] < 5


class TestComputeCalibration:
    def _packets(self, n=5):
        """构造 n 个评测包。评委打分随包变化（否则零方差，Spearman 无意义）。
        真人评委之间做了系统性偏移：r1 恒定比 r2 高 1 分——量纲偏移不影响秩相关。"""
        packets = []
        for i in range(n):
            ai = {"structure": 70 + i, "depth": 60 + 2 * i, "job_match": 65 + i, "written_expression": 75}
            hm = {"structure": 3.0 + i * 0.2, "depth": 2.5 + i * 0.3, "job_match": 3.2, "written_expression": 3.8}
            base = {d: 2 + (i % 3) for d in DIMENSION_KEYS}
            packets.append({
                "ai_scores": ai,
                "human_means": hm,
                "rater_vectors": {
                    "r1": {d: min(5, v + 1) for d, v in base.items()},
                    "r2": dict(base),
                },
            })
        return packets

    def test_end_to_end(self):
        result = compute_calibration(self._packets(), DIMENSION_KEYS)
        assert "overall" in result
        assert "ai_human_rho_mean" in result["overall"]
        assert result["overall"]["ai_human_rho_mean"] > 0  # 构造数据同向递增
        depth = result["per_dimension"]["depth"]
        assert depth["n"] == 5
        assert 0 < depth["spearman_rho"] <= 1
        assert depth["ci95"][0] <= depth["ci95"][1]
        assert depth["badcase_matrix"]

    def test_too_few_packets(self):
        result = compute_calibration(self._packets(2), DIMENSION_KEYS)
        assert "error" in result

    def test_constant_ai_dimension_no_crash(self):
        """AI 在某维度恒定（零方差）→ 输出说明而非 nan（nan 会让 JSON 接口 500）。"""
        packets = []
        for i in range(5):
            base = {d: 2 + (i % 3) for d in DIMENSION_KEYS}
            packets.append({
                "ai_scores": {"structure": 70 + i, "depth": 60, "job_match": 65, "written_expression": 75},  # depth 恒定
                "human_means": {"structure": 3.0 + i * 0.2, "depth": 2.5 + i * 0.3, "job_match": 3.2, "written_expression": 3.8},
                "rater_vectors": {
                    "r1": {d: min(5, v + 1) for d, v in base.items()},
                    "r2": dict(base),
                },
            })
        result = compute_calibration(packets, DIMENSION_KEYS)
        depth = result["per_dimension"]["depth"]
        assert "note" in depth and "无变异" in depth["note"]
        assert "spearman_rho" not in depth
        assert result["overall"]["ai_human_rho_mean"] is not None  # 其他维度仍可统计
        # 整体响应可 JSON 序列化（无 nan）
        import json
        json.dumps(result)
