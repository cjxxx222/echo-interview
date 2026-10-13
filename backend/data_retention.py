"""数据保留策略：面试会话与报告 30 天自动清理。

产品承诺（报告页明示）：面试内容与简历文本不会永久保存，重启/到期即删。
设计取舍：MVP 用内存存储 + 到期清理任务，不落盘——「不存」比「存了再删」更强的隐私姿态。
"""
import time
import asyncio

RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 24 * 3600


def purge_expired_sessions(sessions: dict, reports: dict, now: float | None = None) -> int:
    """清理创建超过 RETENTION_SECONDS 的会话及其报告，返回清理条数。"""
    now = time.time() if now is None else now
    expired = [
        sid for sid, s in sessions.items()
        if now - s.get("start_time", now) > RETENTION_SECONDS
    ]
    for sid in expired:
        sessions.pop(sid, None)
        reports.pop(sid, None)
    return len(expired)


async def retention_loop(get_state) -> None:
    """后台任务：每 6 小时扫一次。get_state() -> (sessions, reports)"""
    while True:
        try:
            purge_expired_sessions(*get_state())
        except Exception as e:
            print(f"[retention] 清理任务异常: {e}")
        await asyncio.sleep(6 * 3600)
