"""In-memory AI activity progress for live UI updates."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

# Canonical stages for customer application analysis
APP_STAGES = [
    {"id": "queued", "label": "Waiting in AI queue"},
    {"id": "starting", "label": "AI analysis starting"},
    {"id": "ocr", "label": "Parsing documents (OCR)"},
    {"id": "llm", "label": "LLM extracting fields"},
    {"id": "validating", "label": "Validating against form"},
    {"id": "report", "label": "Building verification report"},
    {"id": "complete", "label": "AI analysis complete"},
]

_STAGE_INDEX = {s["id"]: i for i, s in enumerate(APP_STAGES)}


class AiProgressStore:
    """Thread-safe progress keyed by application id (or scan job id)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}

    def set(
        self,
        key: str,
        *,
        stage: str,
        message: str,
        detail: str = "",
        done: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = str(key)
        now = time.time()
        with self._lock:
            current = self._items.get(key) or {
                "stage": stage,
                "message": message,
                "detail": detail,
                "done": False,
                "history": [],
                "updated_at": now,
            }
            history: List[dict] = list(current.get("history") or [])
            if not history or history[-1].get("stage") != stage:
                history.append(
                    {
                        "stage": stage,
                        "message": message,
                        "at": now,
                    }
                )
                # Keep history bounded
                history = history[-20:]
            payload = {
                "stage": stage,
                "message": message,
                "detail": detail or "",
                "done": done,
                "history": history,
                "updated_at": now,
            }
            if extra:
                payload.update(extra)
            self._items[key] = payload

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._items.get(str(key))
            return dict(item) if item else None

    def clear(self, key: str) -> None:
        with self._lock:
            self._items.pop(str(key), None)

    def snapshot_for_app(self, application_id: str, status: str) -> Dict[str, Any]:
        """UI-ready progress payload for branch application detail."""
        raw = self.get(application_id)
        if status == "pending" and not raw:
            stage = "queued"
            message = "Waiting in the AI queue…"
            done = False
        elif status == "completed" or status in ("accepted", "rejected"):
            if raw and raw.get("done"):
                stage = raw.get("stage") or "complete"
                message = raw.get("message") or "AI analysis complete."
            else:
                stage = "complete"
                message = "AI analysis complete."
            done = True
        elif raw:
            stage = raw.get("stage") or "starting"
            message = raw.get("message") or "AI is working…"
            done = bool(raw.get("done"))
        else:
            stage = "starting" if status == "analyzing" else "queued"
            message = (
                "AI analysis is running…"
                if status == "analyzing"
                else "Waiting in the AI queue…"
            )
            done = False

        current_idx = _STAGE_INDEX.get(stage, 0)
        steps = []
        for i, s in enumerate(APP_STAGES):
            if done and s["id"] != "complete" and i < _STAGE_INDEX["complete"]:
                state = "done"
            elif done and s["id"] == "complete":
                state = "done"
            elif i < current_idx:
                state = "done"
            elif i == current_idx:
                state = "done" if done else "active"
            else:
                state = "todo"
            steps.append({**s, "state": state})

        messages: List[str] = []
        if raw:
            for h in raw.get("history") or []:
                if h.get("stage") in ("ocr",) and "complete" in (h.get("message") or "").lower():
                    messages.append(h["message"])
                if h.get("stage") in ("llm",) and (
                    "complete" in (h.get("message") or "").lower()
                    or "summary" in (h.get("message") or "").lower()
                ):
                    messages.append(h["message"])
            if raw.get("done"):
                messages.append(raw.get("message") or "AI analysis complete.")

        # Deduplicate while preserving order
        seen = set()
        unique_messages = []
        for m in messages:
            if m and m not in seen:
                seen.add(m)
                unique_messages.append(m)

        return {
            "stage": stage,
            "message": message,
            "detail": (raw or {}).get("detail") or "",
            "done": done,
            "steps": steps,
            "messages": unique_messages[-5:],
            "ai_working": status in ("pending", "analyzing") and not done,
        }


ai_progress = AiProgressStore()
