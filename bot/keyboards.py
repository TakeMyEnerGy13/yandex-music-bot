from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

NUMBER_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def track_keyboard(track_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Похожие треки", callback_data=f"similar:{track_id}")
    builder.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/track/{track_id}")
    builder.adjust(1)
    return builder.as_markup()


def inline_track_keyboard(track_id: str, bot_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Похожие треки", url=f"https://t.me/{bot_username}?start=similar_{track_id}")
    builder.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/track/{track_id}")
    builder.adjust(1)
    return builder.as_markup()


def similar_drilldown_keyboard(track_ids: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, track_id in enumerate(track_ids[:5]):
        builder.button(text=NUMBER_EMOJI[index], callback_data=f"track_card:{track_id}")
    builder.adjust(5)
    return builder.as_markup()


def album_open_keyboard(album_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/album/{album_id}")
    return builder.as_markup()


def artist_open_keyboard(artist_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/artist/{artist_id}")
    return builder.as_markup()


def playlist_open_keyboard(owner: str, kind: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="▶️ Открыть в Яндекс.Музыке",
        url=f"https://music.yandex.ru/users/{owner}/playlists/{kind}",
    )
    return builder.as_markup()
