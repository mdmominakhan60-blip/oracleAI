"""OpenAI-совместимая линия (custom-провайдер, OmniRouter): полный цикл.

`core/llm._run_openai_like` — путь, которым бот разговаривает с любым
OpenAI-совместимым шлюзом вроде OmniRouter. Здесь этот путь проверяется на
локальном in-process сервере, который ведёт себя как настоящий шлюз:
SSE-поток, function calling для скиллов, usage-чанк и отказ от
`stream_options` (фолбэк, когда прокси параметр не знает).

Без внешней сети: сервер поднимается на 127.0.0.1 с случайным портом.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core import llm


# ─────────────────── in-process OpenAI-совместимый сервер ────────────────────

class FakeGateway:
    """Ведёт себя как OpenAI `/v1/chat/completions` с потоком.

    Один экземпляр — один вызов `create`: подсчитывает запросы, решает, вернуть
    ли tool_calls (первый вызов агентного цикла) или ответ текстом (когда уже
    есть результат скилла в истории).
    """

    def __init__(self, *, tool_name: str = "", reject_stream_options: bool = False):
        self.tool_name = tool_name
        self.reject_stream_options = reject_stream_options
        self.requests: list[dict] = []
        self.calls = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}/v1"

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self._port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            await self._serve(reader, writer)
        except Exception as e:  # noqa: BLE001
            print(f"[gateway] hander error: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def _serve(self, reader, writer):
        raw = await reader.readuntil(b"\r\n\r\n")
        headers = raw.decode()
        length = 0
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":")[1])
        body = await reader.readexactly(length)
        request = json.loads(body)
        self.requests.append(request)
        self.calls += 1
        if self.reject_stream_options and "stream_options" in request:
            # llm падает на 400 «stream_options» → повторяет запрос без него.
            # Без Content-Length: SDK дочитывает тело до EOF и видит текст ошибки.
            writer.write(
                b"HTTP/1.1 400 Bad Request\r\n"
                b"Content-Type: application/json\r\n\r\n")
            writer.write(json.dumps({
                "error": {"message": "stream_options not supported by this proxy"}
            }).encode())
            await writer.drain()
            writer.close()
            return

        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n")
        own_tool_round = any(m.get("role") == "tool" for m in request["messages"])
        if self.tool_name and not own_tool_round:
            await self._event(writer, {"choices": [{"index": 0, "delta": {
                "role": "assistant",
                "tool_calls": [{"index": 0, "id": "call_x1", "type": "function",
                                "function": {"name": self.tool_name,
                                             "arguments": ""}}]}}]})
            await self._event(writer, {"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}}]})
        else:
            for piece in ("Привет, смотрю твою карту. ", "Вижу знак — ",
                          "Козерог ", "и это многое объясняет."):
                await self._event(writer, {"choices": [
                    {"index": 0, "delta": {"content": piece}}]})
        # расход токенов — как у настоящих API (только в последнем чанке)
        await self._event(writer, {"choices": [{"index": 0, "delta": {}}],
                                   "usage": {"prompt_tokens": 41,
                                             "completion_tokens": 17}})
        writer.write(b"data: [DONE]\n\n")
        await writer.drain()
        writer.close()

    async def _event(self, writer, payload):
        data = json.dumps(payload, ensure_ascii=False)
        writer.write(f"data: {data}\n\n".encode())
        await writer.drain()


def _use_custom(monkeypatch, gw: FakeGateway):
    """Направляет LLM-слой на локальный шлюз как единственного провайдера."""
    monkeypatch.setattr(settings, "llm_provider", "custom")
    monkeypatch.setattr(settings, "custom_base_url", gw.base_url)
    monkeypatch.setattr(settings, "custom_api_key", "sk-test")
    monkeypatch.setattr(settings, "custom_model_main", "oc/claude-sonnet-5")
    # _models для custom читает custom_model_lite, дефолт — см. микс:
    monkeypatch.setattr(settings, "custom_model_lite", "oc/claude-sonnet-5")


# ───────────────────────────────── тесты ─────────────────────────────────────

async def test_complete_via_custom_stream(monkeypatch):
    """Простой ответ: поток читается, usage-метр работает, сервер видел модель."""
    gw = FakeGateway()
    await gw.start()
    try:
        _use_custom(monkeypatch, gw)
        text = await llm.complete("Ты — Лилит", "Привет", tier="lite", db=None)
        assert "Козерог" in text
        assert gw.calls == 1
        sent_model = gw.requests[0]["model"]
        assert sent_model == "oc/claude-sonnet-5"
        assert gw.requests[0]["messages"][0]["role"] == "system"
    finally:
        await gw.stop()


async def test_run_agent_skill_loop(monkeypatch):
    """Скиллы: первый вызов модели — tool_calls, исполняем, второй — ответ.

    Проверяет главное: инструменты уходят в OpenAI-формате function calling,
    результат скилла доставляется обратно модели в role=tool, и на выходе —
    текст с опорой на результат.
    """
    gw = FakeGateway(tool_name="get_chart")
    await gw.start()
    try:
        _use_custom(monkeypatch, gw)
        executed = []  # какие скиллы реально исполнились

        async def execute(name: str, args) -> str:
            executed.append(name)
            return json.dumps({"sign": "Козерог"}, ensure_ascii=False)

        tools = [{
            "name": "get_chart", "description": "Карта клиентки",
            "input_schema": {"type": "object", "properties": {}},
        }]
        text = await llm.run_agent(
            "Ты — Лилит", [{"role": "user", "content": "Что по карте?"}],
            tools, execute, tier="main", db=None)

        assert executed == ["get_chart"], "скилл не вызван"
        assert "Козерог" in text, "ответ не опирается на результат скилла"
        assert gw.calls == 2, "ожидали цикл из двух запросов к шлюзу"
        second = gw.requests[1]["messages"]
        roles = [m["role"] for m in second]
        assert "tool" in roles, "результат скилла не вернулся модели"
        tool_msg = next(m for m in second if m["role"] == "tool")
        assert "Козерог" in tool_msg["content"]
    finally:
        await gw.stop()


async def test_stream_options_fallback(monkeypatch):
    """Прокси не знает stream_options → llm повторяет запрос без него."""
    gw = FakeGateway(reject_stream_options=True)
    await gw.start()
    try:
        _use_custom(monkeypatch, gw)
        text = await llm.complete("s", "u", tier="lite", db=None)
        assert "Козерог" in text
        assert gw.calls == 2, "первый заход упал на stream_options, нужен повтор"
        assert "stream_options" not in gw.requests[1]
    finally:
        await gw.stop()


async def test_pretool_respects_chiromant_allowlist(monkeypatch):
    calls = []

    async def fake_gather(execute, wanted):
        calls.extend(wanted)
        return [f"{name}:{args}" for name, args in wanted]

    async def fake_stream(client, model, messages, max_tokens, **kwargs):
        return "Мира отвечает по видимому evidence ладони.", []

    monkeypatch.setattr(llm, "_gather_tools", fake_gather)
    monkeypatch.setattr(llm, "_stream_chat", fake_stream)
    tools = [{"name": "palm_scanner"}]

    text = await llm._run_pretool(
        None, "model", "Ты — Мира", [
            {"role": "user", "content": "Проверь качество фото ладони и линию сердца."}
        ], tools, lambda *_: "", 500, None,
    )

    assert "Мира" in text
    assert [name for name, _ in calls] == ["palm_scanner"]
    assert all(not name.startswith(("get_chart", "get_transits", "draw_tarot", "get_matrix"))
               for name, _ in calls)


@pytest.mark.parametrize("question", [
    "Как переснять фото ладони?",
    "Какие чтения ладони у меня были раньше?",
    "Дай мне вопрос для саморефлексии по ладони",
    "Сравни два моих чтения ладони",
])
async def test_pretool_palm_single_call(monkeypatch, question):
    """Любой ладонный вопрос без function-calling — ровно один вызов palm_scanner."""
    calls = []

    async def fake_gather(execute, wanted):
        calls.extend(wanted)
        return [f"{name}:{args}" for name, args in wanted]

    async def fake_stream(client, model, messages, max_tokens, **kwargs):
        return "Мира отвечает по evidence ладони.", []

    monkeypatch.setattr(llm, "_gather_tools", fake_gather)
    monkeypatch.setattr(llm, "_stream_chat", fake_stream)
    tools = [{"name": "palm_scanner"}]

    text = await llm._run_pretool(
        None, "model", "Ты — Мира",
        [{"role": "user", "content": question}],
        tools, lambda *_: "", 500, None,
    )

    assert "Мира" in text
    assert [name for name, _ in calls] == ["palm_scanner"], \
        f"ожидали один palm_scanner для «{question}»"


async def test_pretool_other_agents_unaffected(monkeypatch):
    """Не-ладонные вопросы не тянут palm_scanner, а общие скиллы сохраняются."""
    calls = []

    async def fake_gather(execute, wanted):
        calls.extend(wanted)
        return [f"{name}" for name, _ in wanted]

    async def fake_stream(client, model, messages, max_tokens, **kwargs):
        return "Лилит отвечает.", []

    monkeypatch.setattr(llm, "_gather_tools", fake_gather)
    monkeypatch.setattr(llm, "_stream_chat", fake_stream)
    tools = [{"name": "get_chart"}, {"name": "palm_scanner"}, {"name": "draw_tarot"}]

    await llm._run_pretool(
        None, "model", "Ты — Лилит",
        [{"role": "user", "content": "Какой у меня знак? Сделай расклад таро."}],
        tools, lambda *_: "", 500, None,
    )

    names = [name for name, _ in calls]
    assert "get_chart" in names and "draw_tarot" in names
    assert "palm_scanner" not in names


async def test_openai_like_budget_exhaust_returns_partial(monkeypatch):
    """Исчерпание бюджета tool-use не уходит в pre-tool и не теряет собранный текст."""
    async def fake_stream(client, model, messages, max_tokens, tools=None, **kwargs):
        return "Лилит уже начала ответ.", [{"name": "get_chart", "args": "{}", "id": "c1"}]

    async def fake_gather(execute, wanted, budget=None):
        return ["данные скилла"]

    def boom(*_args, **_kwargs):
        raise AssertionError("pre-tool не должен вызываться при исчерпании бюджета")

    monkeypatch.setattr(llm, "_openai_client", lambda provider: None)
    monkeypatch.setattr(llm, "_stream_chat", fake_stream)
    monkeypatch.setattr(llm, "_gather_tools", fake_gather)
    monkeypatch.setattr(llm, "_run_pretool", boom)
    budget = llm._WorkflowBudget(timeout=10, max_tool_calls=1, max_cost_usd=1.0)
    tools = [{"name": "get_chart", "description": "Карта",
              "input_schema": {"type": "object", "properties": {}}}]

    text = await llm._run_openai_like(
        "custom", "Ты — Лилит", [{"role": "user", "content": "Привет"}],
        tools, lambda *_: "", "main", 500, llm._Meter(), max_iters=5, budget=budget,
    )

    assert "Лилит уже начала ответ" in text


async def test_gpt5_vision_uses_completion_token_budget(monkeypatch):
    """GPT-5 proxy requires max_completion_tokens for multimodal output."""
    seen: dict[str, object] = {}

    class Completions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"status":"complete"}'))],
            )

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=Completions())

        async def close(self):
            return None

    monkeypatch.setattr(llm, "_openai_client", lambda provider: Client())
    monkeypatch.setattr(settings, "openai_main", "gpt-5-mini")
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "palm", "strict": True,
                         "schema": {"type": "object", "additionalProperties": False}},
    }
    text = await llm._vision_with(
        "openai", "system", "user", "data:image/jpeg;base64,AA==",
        "main", 1600, llm._Meter(), response_format=response_format,
    )

    assert text == '{"status":"complete"}'
    assert seen["max_completion_tokens"] == 1600
    assert "max_tokens" not in seen
    assert seen["response_format"] is response_format
