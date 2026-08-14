import asyncio
import time

from telethon import functions, types


class FolderManager:
    """Создаёт/находит папки и инкрементально наполняет их по мере джойна,
    не дожидаясь конца всего прогона."""

    def __init__(self, client, folder_configs, flush_every=5, flush_interval=15):
        self.client = client
        self.folder_configs = folder_configs  # [{"title": str, "count": int}, ...]
        self.flush_every = flush_every
        self.flush_interval = flush_interval
        self.filters_by_title = {}
        self.pending_since_flush = {cfg["title"]: 0 for cfg in folder_configs}
        self._last_flush = {cfg["title"]: time.monotonic() for cfg in folder_configs}
        self._lock = asyncio.Lock()

    async def init(self):
        existing = await self.client(functions.messages.GetDialogFiltersRequest())
        existing_filters = getattr(existing, "filters", existing)

        used_ids = set()
        by_title = {}
        for f in existing_filters:
            fid = getattr(f, "id", None)
            title = getattr(f, "title", None)
            if fid is not None:
                used_ids.add(fid)
            if title and hasattr(f, "include_peers"):
                by_title[title] = f

        next_id = 2  # id 0/1 зарезервированы под "Все чаты"
        for cfg in self.folder_configs:
            title = cfg["title"]
            if title in by_title:
                self.filters_by_title[title] = by_title[title]
                continue
            while next_id in used_ids:
                next_id += 1
            new_filter = types.DialogFilter(
                id=next_id,
                title=title,
                pinned_peers=[],
                include_peers=[],
                exclude_peers=[],
                contacts=False,
                non_contacts=False,
                groups=False,
                broadcasts=False,
                bots=False,
                exclude_muted=False,
                exclude_read=False,
                exclude_archived=False,
            )
            await self.client(
                functions.messages.UpdateDialogFilterRequest(id=next_id, filter=new_filter)
            )
            self.filters_by_title[title] = new_filter
            used_ids.add(next_id)
            next_id += 1

    def folder_for_index(self, global_index: int):
        cursor = 0
        for cfg in self.folder_configs:
            if global_index < cursor + cfg["count"]:
                return cfg["title"]
            cursor += cfg["count"]
        return None

    async def add(self, title: str, input_peer):
        async with self._lock:
            filt = self.filters_by_title[title]
            filt.include_peers.append(input_peer)
            self.pending_since_flush[title] += 1
            due_count = self.pending_since_flush[title] >= self.flush_every
            due_time = (time.monotonic() - self._last_flush[title]) >= self.flush_interval
            if due_count or due_time:
                await self._flush(title)

    async def _flush(self, title: str):
        filt = self.filters_by_title[title]
        await self.client(functions.messages.UpdateDialogFilterRequest(id=filt.id, filter=filt))
        self.pending_since_flush[title] = 0
        self._last_flush[title] = time.monotonic()

    async def flush_all(self):
        async with self._lock:
            for title in self.filters_by_title:
                if self.pending_since_flush[title] > 0:
                    await self._flush(title)
