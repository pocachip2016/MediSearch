"""shared/quota.py — 날짜별 API 쿼터 추적.

파일 기반(JSON)으로 컨테이너 재시작 내구성 확보.
asyncio 단일 이벤트루프 가정 — 별도 잠금 없음.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class DailyQuotaGuard:
    """하루 N건 API 쿼터 추적기.

    `consume()` 호출 → True 반환 시 요청 진행, False 반환 시 한도 초과(빈 결과 반환).
    날짜(UTC)가 바뀌면 카운트 자동 리셋.
    """

    def __init__(self, limit: int, path: str = "./omdb_quota.json") -> None:
        self.limit = limit
        self.path = Path(path)
        self._date: str = ""
        self._count: int = 0
        self._load()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get("date") == self._today():
                    self._date = data["date"]
                    self._count = int(data.get("count", 0))
                    return
            except Exception:
                pass
        self._date = self._today()
        self._count = 0

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps({"date": self._date, "count": self._count}))
        except Exception as e:
            logger.warning(f"[quota] 저장 실패: {e}")

    def consume(self) -> bool:
        """쿼터 1건 소비. 한도 초과면 False."""
        today = self._today()
        if today != self._date:
            self._date = today
            self._count = 0
            logger.info("[quota] 날짜 변경 — 쿼터 리셋")

        if self._count >= self.limit:
            logger.warning(
                f"[quota] 일일 한도 초과 ({self._count}/{self.limit}) — 요청 건너뜀"
            )
            return False

        self._count += 1
        self._save()
        logger.debug(f"[quota] 사용 {self._count}/{self.limit}")
        return True

    @property
    def remaining(self) -> int:
        if self._today() != self._date:
            return self.limit
        return max(0, self.limit - self._count)
