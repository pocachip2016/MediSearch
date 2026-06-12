"""pipeline/_events.py — trace 이벤트 emit 헬퍼 (런너 공용).

on_event 콜백이 None이면 no-op → 비-trace 경로(기존 evaluate/enrich)는 영향 없음.
SSE/검증 경로에서만 콜백을 주입해 단계별 중간 산출물을 스트리밍한다.
중간 산출물(snippet 등)은 콜백으로 흘려보낼 뿐 DB에는 저장하지 않는다(원본 미저장 원칙).
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

# async (event_type: str, payload: dict) -> None
EventCallback = Optional[Callable[[str, dict], Awaitable[None]]]


async def emit(cb: EventCallback, event_type: str, payload: dict) -> None:
    """on_event 콜백 호출 — None이면 아무 것도 하지 않음."""
    if cb is None:
        return
    await cb(event_type, payload)


def doc_previews(docs: list, limit: int = 5, snippet_len: int = 200) -> list[dict]:
    """검색 doc 리스트 → viewing용 미리보기(절단). DB 저장 대상 아님."""
    out: list[dict] = []
    for d in docs[:limit]:
        text = getattr(d, "text", "") or ""
        out.append({
            "title": d.title,
            "url": d.url,
            "snippet": text[:snippet_len],
        })
    return out
