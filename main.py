import asyncio
import json

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from folders import FolderManager
from joiner import StopAll, join_link
from link_parser import classify_link
from state import StateStore
from throttle import AdaptiveThrottle, ThrottleConfig


def load_links(path: str, fmt: str):
    if fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict) and "link" in item:
                result.append(item["link"])
        return result

    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


async def process_link(client, state, fm, throttles, tcfg, i, link, total_capacity):
    if state.is_done(link):
        return

    if i >= total_capacity:
        state.set(link, status="overflow", reason="beyond_folder_capacity")
        return

    kind, value = classify_link(link)
    if kind is None:
        state.set(link, status="skipped", reason="unparseable_link")
        print(f"[skip] {link}: unparseable")
        return

    target_folder = fm.folder_for_index(i)

    while True:
        throttle = throttles[kind]
        await throttle.wait()
        try:
            status, payload = await join_link(client, kind, value)
            break
        except FloodWaitError as e:
            need_cooldown = throttle.record_flood(e.seconds)
            print(f"[flood:{kind}] {link}: wait {e.seconds}s (delay -> {throttle.delay:.1f}s)")
            await asyncio.sleep(e.seconds + max(2, e.seconds * 0.15))
            if need_cooldown:
                print(f"[cooldown:{kind}] много флудов подряд, пауза {tcfg.cooldown_seconds:.0f}s")
                await asyncio.sleep(tcfg.cooldown_seconds)
                throttle.enter_cooldown()
            continue

    throttle.record_success()

    if status in ("joined", "already"):
        state.set(link, status=status, folder=target_folder)
        if payload is not None and target_folder:
            try:
                input_peer = await client.get_input_entity(payload)
                await fm.add(target_folder, input_peer)
            except Exception as e:
                print(f"[warn] {link}: joined, но не добавлен в папку: {e}")
        print(f"[{status}] {link} -> {target_folder}")
    elif status == "pending_approval":
        state.set(link, status="pending_approval", folder=target_folder)
        print(f"[pending] {link}: заявка отправлена, ждёт одобрения админом")
    else:
        state.set(link, status="skipped", reason=payload)
        print(f"[skip] {link}: {payload}")


async def main():
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    links = load_links(cfg["links_file"], cfg.get("links_format", "txt"))
    state = StateStore(cfg.get("state_file", "state.json"))

    client = TelegramClient(cfg["session_name"], cfg["api_id"], cfg["api_hash"])
    await client.start()

    fm = FolderManager(
        client,
        cfg["folders"],
        flush_every=cfg.get("folder_flush_every", 5),
        flush_interval=cfg.get("folder_flush_interval_sec", 15),
    )
    await fm.init()

    total_capacity = sum(f["count"] for f in cfg["folders"])
    tcfg = ThrottleConfig(**cfg.get("throttle", {}))
    throttles = {
        "public": AdaptiveThrottle("public", tcfg),
        "private": AdaptiveThrottle("private", tcfg),
    }

    try:
        for i, link in enumerate(links):
            await process_link(client, state, fm, throttles, tcfg, i, link, total_capacity)
    except StopAll as e:
        print(f"[STOP] {e}")
    finally:
        await fm.flush_all()
        await client.disconnect()

    joined = state.count_by_status("joined") + state.count_by_status("already")
    skipped = state.count_by_status("skipped")
    pending = state.count_by_status("pending_approval")
    overflow = state.count_by_status("overflow")
    print(
        f"\nГотово. Заджойнено: {joined}/{total_capacity} | "
        f"пропущено: {skipped} | ждут одобрения: {pending} | вне лимита папок: {overflow}"
    )


if __name__ == "__main__":
    asyncio.run(main())
