"""数据保留策略测试：30 天清理的正确性。"""
import time

from data_retention import purge_expired_sessions, RETENTION_SECONDS


class TestPurge:
    def _sessions(self, now):
        return {
            "fresh": {"start_time": now - 60},
            "expired": {"start_time": now - RETENTION_SECONDS - 1},
            "edge": {"start_time": now - RETENTION_SECONDS + 10},  # 未到期
        }

    def test_purge_only_expired(self):
        now = time.time()
        sessions = self._sessions(now)
        reports = {"fresh": object(), "expired": object(), "edge": object()}
        removed = purge_expired_sessions(sessions, reports, now=now)
        assert removed == 1
        assert set(sessions) == {"fresh", "edge"}
        assert set(reports) == {"fresh", "edge"}  # 报告随会话一起清

    def test_no_start_time_not_purged(self):
        now = time.time()
        sessions = {"legacy": {}}
        purge_expired_sessions(sessions, {}, now=now)
        assert "legacy" in sessions  # 缺 start_time 的按 now 处理，不清

    def test_empty(self):
        assert purge_expired_sessions({}, {}, now=time.time()) == 0
