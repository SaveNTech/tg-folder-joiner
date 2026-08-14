import asyncio
import random
from collections import deque
from dataclasses import dataclass


@dataclass
class ThrottleConfig:
    delay_start: float = 4.0
    delay_min: float = 1.5
    delay_max: float = 300.0
    success_decay: float = 0.92
    flood_backoff_mult: float = 2.5
    jitter: float = 0.2
    cooldown_after_floods: int = 3
    cooldown_window: int = 15
    cooldown_seconds: float = 1200.0


class AdaptiveThrottle:
    """AIMD-регулятор темпа запросов одного типа (public join / private invite).

    Разгоняется на успехах, резко тормозит на FloodWait и уходит в
    длинный cooldown при частых флудах подряд — вместо фиксированной паузы.
    """

    def __init__(self, name: str, cfg: ThrottleConfig):
        self.name = name
        self.cfg = cfg
        self.delay = cfg.delay_start
        self.history: deque = deque(maxlen=cfg.cooldown_window)

    async def wait(self):
        jitter = self.delay * self.cfg.jitter
        d = max(self.cfg.delay_min, self.delay + random.uniform(-jitter, jitter))
        await asyncio.sleep(d)

    def record_success(self):
        self.history.append(False)
        self.delay = max(self.cfg.delay_min, self.delay * self.cfg.success_decay)

    def record_flood(self, wait_seconds: float) -> bool:
        """Возвращает True, если нужно уйти в длинный cooldown."""
        self.history.append(True)
        self.delay = min(
            self.cfg.delay_max,
            max(self.delay * self.cfg.flood_backoff_mult, wait_seconds * 0.1),
        )
        return self.history.count(True) >= self.cfg.cooldown_after_floods

    def enter_cooldown(self):
        self.delay = self.cfg.delay_start
        self.history.clear()
