"""Тесты серверной единой истории диалога с Oracle (Stage 4.4 & 4.4.1).

Проверяют:
1. Объединение сообщений из всех 4 поддерживаемых доменов (oracle, astro, tarot, chiromant).
2. Исключение сообщений из архивированных тредов (threads.archived = 1) в том числе при пагинации.
3. Изоляцию пользователей (сообщения чужого tg_id никогда не попадают в ленту).
4. Детерминированный порядок сортировки при совпадающих created_at (по id ASC).
5. Составной keyset-курсор (created_at, id) при несовпадении порядка ID и времени.
6. Многостраничную пагинацию без пропусков и дубликатов.
7. Пустую историю для нового пользователя и 401 для анонимного запроса.
8. Стабильность курсора в прошлое при поступлении новых сообщений (keyset vs offset).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.main import app
from app.services.repo_gateway import dialog, users

TEST_DEV_KEY = "test-dev-key"


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user, params: dict | None = None) -> dict:
    return {"dev_user": user["tg_id"], **(params or {})}


@pytest.mark.asyncio
async def test_unified_history_aggregates_all_four_agents(client, db, user):
    """Сообщения из тредов всех 4 доменов собираются в единую хронологию."""
    tg_id = user["tg_id"]

    # Создаем треды для 4 доменов
    t_oracle = await dialog.create_thread(db, tg_id, agent="oracle", title="Общий разговор")
    t_tarot = await dialog.create_thread(db, tg_id, agent="tarot", title="Расклад")
    t_astro = await dialog.create_thread(db, tg_id, agent="astro", title="Карта")
    t_chiro = await dialog.create_thread(db, tg_id, agent="chiromant", title="Линии руки")

    # Добавляем сообщения с разными временными метками
    await dialog.save_message(db, tg_id, "user", "Привет, Лилит", thread_id=t_oracle["id"], agent="oracle")
    await dialog.save_message(db, tg_id, "assistant", "Здравствуй, душа", thread_id=t_oracle["id"], agent="oracle")
    await dialog.save_message(db, tg_id, "user", "Сделай расклад", thread_id=t_tarot["id"], agent="tarot")
    await dialog.save_message(db, tg_id, "assistant", "Выпал Шут", thread_id=t_tarot["id"], agent="tarot")
    await dialog.save_message(db, tg_id, "user", "Где мой Марс?", thread_id=t_astro["id"], agent="astro")
    await dialog.save_message(db, tg_id, "assistant", "Марс в Овне", thread_id=t_astro["id"], agent="astro")
    await dialog.save_message(db, tg_id, "user", "Посмотри ладонь", thread_id=t_chiro["id"], agent="chiromant")
    await dialog.save_message(db, tg_id, "assistant", "Линия жизни глубокая", thread_id=t_chiro["id"], agent="chiromant")

    res = await client.get("/api/chat/history/unified", params=as_user(user))
    assert res.status_code == 200
    data = res.json()

    messages = data["messages"]
    assert len(messages) == 8
    agents_in_feed = {m["agent"] for m in messages}
    assert agents_in_feed == {"oracle", "tarot", "astro", "chiromant"}
    assert data["has_more"] is False
    assert data["missing"] == []

    # Алиас /api/chat/unified возвращает точно такой же результат
    alias_res = await client.get("/api/chat/unified", params=as_user(user))
    assert alias_res.status_code == 200
    assert len(alias_res.json()["messages"]) == 8


@pytest.mark.asyncio
async def test_unified_history_excludes_archived_threads(client, db, user):
    """Сообщения из тредов с archived=1 не попадают в активную историю."""
    tg_id = user["tg_id"]

    t_active = await dialog.create_thread(db, tg_id, agent="oracle", title="Живой диалог")
    t_archived = await dialog.create_thread(db, tg_id, agent="tarot", title="Старый чат")

    await dialog.save_message(db, tg_id, "user", "Активное сообщение", thread_id=t_active["id"], agent="oracle")
    await dialog.save_message(db, tg_id, "user", "Архивное сообщение", thread_id=t_archived["id"], agent="tarot")

    # Архивируем второй тред
    await dialog.archive_thread(db, t_archived["id"], tg_id)

    res = await client.get("/api/chat/history/unified", params=as_user(user))
    assert res.status_code == 200
    messages = res.json()["messages"]

    assert len(messages) == 1
    assert messages[0]["text"] == "Активное сообщение"
    assert messages[0]["thread_id"] == t_active["id"]


@pytest.mark.asyncio
async def test_unified_history_user_isolation(client, db, user):
    """Пользователь А никогда не видит сообщения пользователя Б."""
    user_b = await users.ensure(db, 999111, name="Другой пользователь")

    t_a = await dialog.create_thread(db, user["tg_id"], agent="oracle", title="Чат А")
    t_b = await dialog.create_thread(db, user_b["tg_id"], agent="oracle", title="Чат Б")

    await dialog.save_message(db, user["tg_id"], "user", "Секрет пользователя А", thread_id=t_a["id"])
    await dialog.save_message(db, user_b["tg_id"], "user", "Секрет пользователя Б", thread_id=t_b["id"])

    # Запрос от пользователя А
    res_a = await client.get("/api/chat/history/unified", params=as_user(user))
    assert res_a.status_code == 200
    texts_a = [m["text"] for m in res_a.json()["messages"]]
    assert "Секрет пользователя А" in texts_a
    assert "Секрет пользователя Б" not in texts_a

    # Запрос от пользователя Б
    res_b = await client.get("/api/chat/history/unified", params=as_user(user_b))
    assert res_b.status_code == 200
    texts_b = [m["text"] for m in res_b.json()["messages"]]
    assert "Секрет пользователя Б" in texts_b
    assert "Секрет пользователя А" not in texts_b


@pytest.mark.asyncio
async def test_unified_history_deterministic_tie_breaker(client, db, user):
    """При одинаковых created_at порядок детерминирован по id ASC."""
    tg_id = user["tg_id"]
    t = await dialog.create_thread(db, tg_id, agent="oracle")

    # Вставляем напрямую с одинаковым created_at
    same_time = "2026-10-12T12:00:00.000000+00:00"
    cur = await db.execute(
        "INSERT INTO messages(tg_id, thread_id, agent, role, text, created_at) "
        "VALUES(:tg_id, :t_id, 'oracle', 'user', 'Первое по id', :time) RETURNING id",
        {"tg_id": tg_id, "t_id": t["id"], "time": same_time},
    )
    id1 = (await cur.fetchone())["id"]

    cur2 = await db.execute(
        "INSERT INTO messages(tg_id, thread_id, agent, role, text, created_at) "
        "VALUES(:tg_id, :t_id, 'oracle', 'assistant', 'Второе по id', :time) RETURNING id",
        {"tg_id": tg_id, "t_id": t["id"], "time": same_time},
    )
    id2 = (await cur2.fetchone())["id"]

    res = await client.get("/api/chat/history/unified", params=as_user(user))
    assert res.status_code == 200
    messages = res.json()["messages"]

    assert len(messages) == 2
    assert messages[0]["id"] == id1
    assert messages[0]["text"] == "Первое по id"
    assert messages[1]["id"] == id2
    assert messages[1]["text"] == "Второе по id"


@pytest.mark.asyncio
async def test_unified_history_composite_keyset_inverted_id_order(client, db, user):
    """Критический регрессионный тест Stage 4.4.1:
    Порядок ID противоположен порядку created_at (например, при асинхронных вставках,
    импорте или дрейфе часов).
    Составной курсор (created_at, id) обязан корректно вернуть все сообщения,
    тогда как наивный id < before_id потерял бы сообщения со старшим ID.
    """
    tg_id = user["tg_id"]
    t = await dialog.create_thread(db, tg_id, agent="oracle")

    # m_recent: новейшее по времени, но с МЕНЬШИМ id
    # m_older: более старое по времени, но с БОЛЬШИМ id
    # m_oldest: самое старое
    t_recent = "2026-10-12T12:00:00.000000+00:00"
    t_older = "2026-10-12T10:00:00.000000+00:00"
    t_oldest = "2026-10-12T08:00:00.000000+00:00"

    # Вставляем сообщение 1 (старое по времени)
    cur = await db.execute(
        "INSERT INTO messages(tg_id, thread_id, agent, role, text, created_at) "
        "VALUES(:tg_id, :t_id, 'oracle', 'user', 'Старое время, меньший ID', :time) RETURNING id",
        {"tg_id": tg_id, "t_id": t["id"], "time": t_older},
    )
    id_older_small = (await cur.fetchone())["id"]

    # Вставляем сообщение 2 (новейшее по времени)
    cur = await db.execute(
        "INSERT INTO messages(tg_id, thread_id, agent, role, text, created_at) "
        "VALUES(:tg_id, :t_id, 'oracle', 'user', 'Новое время', :time) RETURNING id",
        {"tg_id": tg_id, "t_id": t["id"], "time": t_recent},
    )
    id_recent = (await cur.fetchone())["id"]

    # Вставляем сообщение 3 (самое старое по времени, но с САМЫМ БОЛЬШИМ id!)
    cur = await db.execute(
        "INSERT INTO messages(tg_id, thread_id, agent, role, text, created_at) "
        "VALUES(:tg_id, :t_id, 'oracle', 'user', 'Самое старое время, но большой ID', :time) RETURNING id",
        {"tg_id": tg_id, "t_id": t["id"], "time": t_oldest},
    )
    id_oldest_large = (await cur.fetchone())["id"]
    assert id_oldest_large > id_older_small

    # Страница 1 (limit=2): должна вернуть id_recent и id_older_small
    res1 = await client.get("/api/chat/history/unified", params=as_user(user, {"limit": 2}))
    assert res1.status_code == 200
    d1 = res1.json()
    assert len(d1["messages"]) == 2
    assert d1["has_more"] is True
    # В прямой хронологии страницы 1: [id_older_small, id_recent]
    assert d1["messages"][0]["id"] == id_older_small
    assert d1["messages"][1]["id"] == id_recent

    oldest_id = d1["oldest_id"]
    oldest_created_at = d1["oldest_created_at"]
    assert oldest_id == id_older_small
    assert oldest_created_at == t_older

    # Страница 2: запрашиваем перед (oldest_created_at, oldest_id)
    # Если бы фильтр был `id < oldest_id`, id_oldest_large был бы отсечен, т.к. его id > id_older_small!
    res2 = await client.get("/api/chat/history/unified", params=as_user(user, {
        "limit": 2,
        "before_id": oldest_id,
        "before_created_at": oldest_created_at,
    }))
    assert res2.status_code == 200
    d2 = res2.json()
    assert len(d2["messages"]) == 1
    assert d2["messages"][0]["id"] == id_oldest_large
    assert d2["messages"][0]["text"] == "Самое старое время, но большой ID"
    assert d2["has_more"] is False

    # Проверяем также обратную совместимость (fallback только с before_id, сервер сам находит created_at)
    res2_compat = await client.get("/api/chat/history/unified", params=as_user(user, {
        "limit": 2,
        "before_id": oldest_id,
    }))
    assert res2_compat.status_code == 200
    assert len(res2_compat.json()["messages"]) == 1
    assert res2_compat.json()["messages"][0]["id"] == id_oldest_large


@pytest.mark.asyncio
async def test_unified_history_multi_page_no_gaps_or_duplicates(client, db, user):
    """Многостраничная keyset-пагинация: собирает всю историю без пропусков и дублей."""
    tg_id = user["tg_id"]
    t = await dialog.create_thread(db, tg_id, agent="oracle")

    # Создаем 10 сообщений
    created_ids = []
    for i in range(10):
        mid = await dialog.save_message(db, tg_id, "user", f"Сообщение #{i+1}", thread_id=t["id"])
        created_ids.append(mid)

    # Читаем страницами по limit=3
    all_retrieved = []
    before_id = None
    before_created_at = None

    for _ in range(5):  # максимум 5 страниц для 10 элементов
        params = {"limit": 3}
        if before_id is not None:
            params["before_id"] = before_id
            params["before_created_at"] = before_created_at
        res = await client.get("/api/chat/history/unified", params=as_user(user, params))
        assert res.status_code == 200
        data = res.json()
        msgs = data["messages"]
        all_retrieved = msgs + all_retrieved  # склеиваем в хронологическом порядке
        if not data["has_more"]:
            break
        before_id = data["oldest_id"]
        before_created_at = data["oldest_created_at"]

    retrieved_ids = [m["id"] for m in all_retrieved]
    assert len(retrieved_ids) == 10
    # Нет дубликатов
    assert len(set(retrieved_ids)) == 10
    # Все созданные ID присутствуют
    assert retrieved_ids == created_ids


@pytest.mark.asyncio
async def test_unified_history_empty_and_unauthorized(client, user):
    """Пустая история для нового пользователя и 401 для анонимного запроса."""
    # Пустая история
    res = await client.get("/api/chat/history/unified", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["messages"] == []
    assert data["has_more"] is False
    assert data["oldest_id"] is None
    assert data["oldest_created_at"] is None
    assert data["newest_id"] is None
    assert data["newest_created_at"] is None
    assert data["missing"] == []

    # Анонимный запрос (без dev_user и без токена)
    anon = await client.get("/api/chat/history/unified")
    assert anon.status_code == 401


@pytest.mark.asyncio
async def test_unified_history_mid_pagination_inserts_stability(client, db, user):
    """Добавление новых сообщений во время чтения не сдвигает keyset-курсор в прошлое."""
    tg_id = user["tg_id"]
    t = await dialog.create_thread(db, tg_id, agent="oracle")

    # Вставляем 4 сообщения: m1, m2, m3, m4
    m1 = await dialog.save_message(db, tg_id, "user", "m1", thread_id=t["id"])
    m2 = await dialog.save_message(db, tg_id, "user", "m2", thread_id=t["id"])
    m3 = await dialog.save_message(db, tg_id, "user", "m3", thread_id=t["id"])
    m4 = await dialog.save_message(db, tg_id, "user", "m4", thread_id=t["id"])

    # Читаем страницу 1 (limit=2): получаем [m3, m4]
    p1 = await client.get("/api/chat/history/unified", params=as_user(user, {"limit": 2}))
    d1 = p1.json()
    assert [m["id"] for m in d1["messages"]] == [m3, m4]

    # Пока пользователь читает, приходит новое сообщение m5 (больший created_at/id)
    await dialog.save_message(db, tg_id, "assistant", "m5 (new)", thread_id=t["id"])

    # Запрашиваем страницу 2 в прошлое с сохраненным курсором d1["oldest_id"] (m3)
    p2 = await client.get("/api/chat/history/unified", params=as_user(user, {
        "limit": 2,
        "before_id": d1["oldest_id"],
        "before_created_at": d1["oldest_created_at"],
    }))
    d2 = p2.json()
    # При OFFSET пагинации смещение сдвинулось бы и повторило m3.
    # При keyset-пагинации получаем строго предшествующие: [m1, m2] без сдвига!
    assert [m["id"] for m in d2["messages"]] == [m1, m2]
