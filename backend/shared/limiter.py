"""동시성 게이트 + 도메인 throttle — Ollama/Namu.wiki 부하 제어."""
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class EvalBusyError(Exception):
    """평가 대기열이 가득 차면 발생."""
    pass


class EvalGate:
    """Ollama 평가 직렬화 — 최대 N건 동시 실행, 초과 시 timeout 후 429 반환."""

    def __init__(self, max_concurrent: int = 1, queue_timeout_s: float = 300):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue_timeout_s = queue_timeout_s

    async def __aenter__(self):
        try:
            await asyncio.wait_for(
                self.semaphore.acquire(), timeout=self.queue_timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[EvalGate] 대기열 타임아웃 ({self.queue_timeout_s}s 초과)"
            )
            raise EvalBusyError("Evaluation queue timeout") from None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.semaphore.release()
        return False


class DomainThrottle:
    """도메인별 최소 간격 throttle — asyncio.Lock + monotonic."""

    def __init__(self, min_interval_s: float = 20.0):
        self.min_interval_s = min_interval_s
        self.lock = asyncio.Lock()
        self.last_hit = 0.0

    async def wait(self):
        """최소 간격이 경과할 때까지 대기."""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_hit
            if elapsed < self.min_interval_s:
                wait_s = self.min_interval_s - elapsed
                logger.debug(
                    f"[Throttle] {self.min_interval_s}s 간격 유지 — {wait_s:.1f}s 대기"
                )
                await asyncio.sleep(wait_s)
            self.last_hit = time.monotonic()
