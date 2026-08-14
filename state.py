import json
import os
import threading

TERMINAL_STATUSES = {"joined", "already", "skipped", "pending_approval", "overflow"}
SUCCESS_STATUSES = {"joined", "already"}


class StateStore:
    """Персистентный прогресс по каждой ссылке, чтобы прогон можно было
    прерывать и продолжать без повторной обработки уже решённых ссылок."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"links": {}}

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def get(self, link: str):
        return self.data["links"].get(link)

    def is_done(self, link: str) -> bool:
        entry = self.get(link)
        return bool(entry and entry.get("status") in TERMINAL_STATUSES)

    def set(self, link: str, **fields):
        entry = self.data["links"].setdefault(link, {})
        entry.update(fields)
        self.save()

    def count_by_status(self, status: str) -> int:
        return sum(1 for v in self.data["links"].values() if v.get("status") == status)
