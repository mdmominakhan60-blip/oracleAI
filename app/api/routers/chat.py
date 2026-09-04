"""Чаты с агентами: список, история, вопрос."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from ...core import agents
from ...services import chat as chat_svc
from ...services.repo_gateway import dialog
from ..common.errors import access_denied
from ..contracts.chat import AskIn
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["chat"])

@router.get("/agents")
async def agent_list(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Список чатов: агент, превью последнего сообщения, подсказки."""
    return await chat_svc.threads_view(db, user)


@router.get("/chat")
async def chat_history_default(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Совместимость: общая лента диалога с Оракулом."""
    messages = await dialog.history(db, user["tg_id"], limit=30)
    return {"messages": messages}


@router.get("/chat/{agent}")
async def chat_history(agent: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    return await chat_svc.thread_history(db, user, agent)


@router.post("/chat/{agent}", dependencies=[Depends(rate_limit("llm"))])
async def ask_agent(agent: str, item: AskIn, user=Depends(confirmed_age_user),
                    db=Depends(get_db), x_idempotency_key: str | None = Header(default=None)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    try:
        return await chat_svc.ask(db, user, item.text, agent=agent,
                                  surface="miniapp", allow_paid=item.allow_paid,
                                  idempotency_key=x_idempotency_key)
    except chat_svc.ChatDenied as e:
        raise access_denied(e.verdict, lang=user["lang"] or "ru") from e
    except chat_svc.ChatRequestInProgress as e:
        raise HTTPException(409, detail={"code": "request_in_progress", "message": str(e)}) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/ask", dependencies=[Depends(rate_limit("llm"))])
async def ask(item: AskIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Совместимость: вопрос главному Оракулу."""
    try:
        result = await chat_svc.ask(db, user, item.text,
                                   agent=agents.DEFAULT_AGENT, surface="miniapp")
    except chat_svc.ChatDenied as e:
        raise access_denied(e.verdict, lang=user["lang"] or "ru") from e
    return {"answer": result["answer"],
            "questions_left": result["allowance"]["left"],
            "allowance": result["allowance"]}


@router.delete("/chat/{agent}", dependencies=[Depends(rate_limit("write"))])
async def clear_thread(agent: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Архивирует переписку: новый чат начнётся с чистого листа.

    Сообщения не удаляются — память о клиентке и история для поддержки остаются.
    """
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    thread = await dialog.ensure_thread(db, user["tg_id"], agent)
    await dialog.archive_thread(db, thread["id"], user["tg_id"])
    return {"ok": True}


# ─────────────────── многочатовые сессии (как ChatGPT) ───────────────────────


@router.get("/chat/{agent}/sessions")
async def list_sessions(agent: str, user=Depends(confirmed_age_user), db=Depends(get_db),
                        offset: int = Query(default=0, ge=0)):
    """Активные чаты агента — новые впереди, страницами по 100 (аудит API-014):
    у активного пользователя с сотнями чатов полный список грузился на каждый
    рендер. `offset` листает дальше первой страницы.
    """
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    rows = [dict(r) for r in await dialog.list_threads(db, user["tg_id"], limit=100,
                                                       offset=offset)
            if r["agent"] == agent]
    return rows


@router.post("/chat/{agent}/sessions", dependencies=[Depends(rate_limit("write"))])
async def new_session(agent: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    spec = agents.get(agent)
    thread = await dialog.create_thread(db, user["tg_id"], spec.code,
                                        title=spec.title)
    return {"thread_id": thread["id"], "title": spec.title}


@router.delete("/chat/{agent}/sessions", dependencies=[Depends(rate_limit("write"))])
async def delete_all_sessions(agent: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Архивирует все чаты агента; сообщения и личная память сохраняются."""
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    archived = await dialog.archive_all_threads(db, user["tg_id"], agent)
    return {"ok": True, "archived": archived, "memory_preserved": True}


@router.get("/chat/{agent}/sessions/{thread_id}")
async def session_history(agent: str, thread_id: int, user=Depends(confirmed_age_user),
                          db=Depends(get_db)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    thread = await dialog.get_thread(db, thread_id, user["tg_id"])
    if not thread or thread["agent"] != agent or thread["archived"]:
        raise HTTPException(404, "нет такого чата")
    messages = await dialog.thread_messages(db, thread_id, limit=60)
    return {"agent": agents.get(agent).as_dict(user), "thread_id": thread_id,
            "messages": messages}


@router.post("/chat/{agent}/sessions/{thread_id}",
             dependencies=[Depends(rate_limit("llm"))])
async def ask_session(agent: str, thread_id: int, item: AskIn,
                      user=Depends(confirmed_age_user), db=Depends(get_db),
                      x_idempotency_key: str | None = Header(default=None)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    try:
        return await chat_svc.ask(db, user, item.text, agent=agent,
                                  surface="miniapp",                                   allow_paid=item.allow_paid,
                                  thread_id=thread_id,
                                  idempotency_key=x_idempotency_key)

    except chat_svc.ChatDenied as e:
        raise access_denied(e.verdict, lang=user["lang"] or "ru") from e
    except chat_svc.ChatRequestInProgress as e:
        raise HTTPException(409, detail={"code": "request_in_progress", "message": str(e)}) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/chat/{agent}/sessions/{thread_id}",
               dependencies=[Depends(rate_limit("write"))])
async def delete_session(agent: str, thread_id: int, user=Depends(confirmed_age_user),
                         db=Depends(get_db)):
    thread = await dialog.get_thread(db, thread_id, user["tg_id"])
    if not thread or thread["agent"] != agent:
        raise HTTPException(404, "нет такого чата")
    await dialog.archive_thread(db, thread_id, user["tg_id"])
    return {"ok": True}
