import asyncio
from types import SimpleNamespace

from telegram_bot.app import handle_request, main_keyboard, server_photo_consent, welcome


class FakeState:
    def __init__(self):
        self.data = {}
    async def update_data(self, **kwargs):
        self.data.update(kwargs)


class FakeMessage:
    def __init__(self):
        self.calls = []
    async def answer(self, text, **kwargs):
        self.calls.append({"text": text, **kwargs})


def test_start_always_exposes_local_mini_app_without_policy(monkeypatch):
    monkeypatch.delenv("PRIVACY_URL", raising=False)
    monkeypatch.setenv("MINI_APP_URL", "https://aoptica72.github.io/aoptika-tryon/telegram.html")
    message = FakeMessage()
    asyncio.run(welcome(message, FakeState()))
    assert "не отправляется боту или на сервер" in message.calls[0]["text"]
    keyboard = message.calls[0]["reply_markup"]
    assert keyboard.keyboard[0][0].web_app.url.endswith("/telegram.html")


def test_direct_chat_photo_is_disabled_until_policy_is_published(monkeypatch):
    monkeypatch.delenv("PRIVACY_URL", raising=False)
    message = FakeMessage()
    asyncio.run(server_photo_consent(message, FakeState()))
    assert "пока отключена" in message.calls[0]["text"]
    assert "reply_markup" not in message.calls[0]


def test_stock_action_requests_contact_consent(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "123456")
    monkeypatch.setenv("PRIVACY_URL", "https://aoptica.ru/published-policy")
    message, state = FakeMessage(), FakeState()
    asyncio.run(handle_request(message, state, None, "stock"))
    assert state.data["pending_action"] == "stock"
    assert state.data["contact_consent"] is False
    assert "запроса наличия" in message.calls[0]["text"]
    assert message.calls[0]["reply_markup"] is not None


def test_leads_are_blocked_without_published_policy(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "123456")
    monkeypatch.delenv("PRIVACY_URL", raising=False)
    message, state = FakeMessage(), FakeState()
    asyncio.run(handle_request(message, state, None, "booking"))
    assert "политика обработки данных не настроена" in message.calls[0]["text"]
    assert "pending_action" not in state.data


def test_main_keyboard_uses_https_and_web_app_button(monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://example.com/telegram.html")
    keyboard = main_keyboard()
    button = keyboard.keyboard[0][0]
    assert button.text == "👓 Примерить очки"
    assert button.web_app.url == "https://example.com/telegram.html"
