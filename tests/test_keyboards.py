from bot.keyboards import similar_drilldown_keyboard, track_keyboard


def test_track_keyboard_has_similar_and_open_buttons():
    keyboard = track_keyboard(track_id="456")
    rows = keyboard.inline_keyboard
    assert len(rows) >= 1
    flat = [button for row in rows for button in row]
    callback_buttons = [button for button in flat if button.callback_data]
    url_buttons = [button for button in flat if button.url]
    assert any(button.callback_data == "similar:456" for button in callback_buttons)
    assert any("music.yandex.ru/track/456" in button.url for button in url_buttons)


def test_similar_drilldown_has_five_numeric_buttons():
    keyboard = similar_drilldown_keyboard(["1", "2", "3", "4", "5"])
    flat = [button for row in keyboard.inline_keyboard for button in row]
    assert len(flat) == 5
    assert {button.text for button in flat} == {"1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"}
    assert [button.callback_data for button in flat] == [
        "track_card:1",
        "track_card:2",
        "track_card:3",
        "track_card:4",
        "track_card:5",
    ]
