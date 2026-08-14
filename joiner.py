from telethon import functions
from telethon.errors import (
    AuthKeyError,
    ChannelPrivateError,
    ChannelsTooMuchError,
    ChatAdminRequiredError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)


class StopAll(Exception):
    """Фатальная для всего прогона ситуация (лимит диалогов, бан, спам-флаг)."""


async def join_link(client, kind: str, value: str):
    """Пытается вступить в чат. Возвращает (status, payload).

    status: "joined" | "already" | "pending_approval" | "skipped"
    payload: entity (для joined/already) или строка-причина (для skipped).

    FloodWaitError намеренно не перехватывается здесь — её должен
    обработать вызывающий код (throttle + ретрай той же ссылки).
    """
    if kind == "private":
        req = functions.messages.ImportChatInviteRequest(value)
    elif kind == "public":
        req = functions.channels.JoinChannelRequest(value)
    else:
        return "skipped", "unrecognized_link"

    try:
        result = await client(req)
        chats = getattr(result, "chats", None)
        return "joined", (chats[0] if chats else None)

    except UserAlreadyParticipantError:
        if kind == "private":
            check = await client(functions.messages.CheckChatInviteRequest(value))
            return "already", getattr(check, "chat", None)
        entity = await client.get_entity(value)
        return "already", entity

    except InviteRequestSentError:
        return "pending_approval", None

    except (
        InviteHashExpiredError,
        InviteHashInvalidError,
        UsernameNotOccupiedError,
        UsernameInvalidError,
        ChannelPrivateError,
        ChatAdminRequiredError,
        UserBannedInChannelError,
    ) as e:
        return "skipped", type(e).__name__

    except ChannelsTooMuchError:
        raise StopAll("CHANNELS_TOO_MUCH: аккаунт упёрся в лимит диалогов (500/1000)")

    except (UserDeactivatedBanError, UserDeactivatedError, AuthKeyError) as e:
        raise StopAll(f"account_fatal:{type(e).__name__}")

    except PeerFloodError:
        raise StopAll("PEER_FLOOD: аккаунт словил спам-ограничение, останов")
