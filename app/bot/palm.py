"""Unified Telegram intake for Mira palm images."""
from __future__ import annotations

from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..core import palm as palm_core
from ..repo import users
from .features import PALM_TOPIC_LABELS, PalmUpload
from .keyboards import back_menu
from .ui import BotStage, begin_status

router = Router()
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


async def _run(message: Message, state: FSMContext, db, image: bytes, content_type: str | None) -> None:
    user = await users.get(db, message.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    await message.answer("✋ Фото получено. Проверяю качество…" if lang == "ru" else "✋ Photo received. Checking quality…")
    status = await begin_status(
        message,
        user,
        BotStage.USING_TOOL,
        "Мира проверяет качество снимка…" if lang == "ru" else "Mira is checking the photo quality…",
    )
    try:
        result = await palm_core.analyze_and_save(db, user, image, surface="bot", content_type=content_type)
    except ValueError as exc:
        await status.set(BotStage.RECOVERABLE_ERROR, "Invalid image" if lang == "en" else "Некорректное изображение")
        await message.answer(
            f"✋ {exc}\n\nJPEG, PNG или WebP — одна ладонь целиком, при ровном свете." if lang == "ru"
            else f"✋ {exc}\n\nSend one whole palm as JPEG, PNG or WebP in even light.",
            reply_markup=back_menu(),
        )
        return
    except Exception:
        await status.set(BotStage.RECOVERABLE_ERROR, "Technical failure" if lang == "en" else "Технический сбой")
        await message.answer(
            "Мира получила изображение, но не смогла закончить обработку. Попробуй ещё раз немного позже."
            if lang == "ru" else
            "Mira received the image but could not finish processing it. Please try again later.",
            reply_markup=back_menu(),
        )
        return

    error_code = result.get("error_code")
    if error_code:
        await status.set(BotStage.RECOVERABLE_ERROR, error_code)
        if error_code == palm_core.PHOTO_LOW_QUALITY:
            issues = result.get("image_quality", {}).get("issues") or []
            readable = {
                "underexposed": "слишком темно", "overexposed": "слишком светло",
                "low_resolution": "низкое разрешение", "low_contrast_or_flat_light": "мало контраста",
                "soft_or_blurred_edges": "снимок мягкий или смазан", "extreme_crop_or_aspect": "ладонь обрезана",
            }
            reasons = "\n".join(f"• {readable.get(str(x), str(x))}" for x in issues[:3])
            text = (
                "✋ Кадр пока не подходит.\n"
                f"Почему:\n{reasons or '• недостаточно визуальной информации'}\n\n"
                "Как исправить:\n• больше ровного света\n• вся ладонь целиком\n• без бликов и фильтров"
            ) if lang == "ru" else (
                "✋ The frame is not clear enough yet.\n"
                f"Why:\n{reasons or '• not enough visual information'}\n\n"
                "Try:\n• more even light\n• whole palm in frame\n• no glare or filters"
            )
        elif error_code == palm_core.VISION_SCHEMA_INVALID:
            text = (
                "✋ Фото хорошее, но чтение сейчас не удалось собрать. Попробуй ещё раз — переснимать не нужно."
                if lang == "ru" else
                "✋ The photo is good, but I could not assemble the reading. Please try again — no reshoot is needed."
            )
        elif error_code == palm_core.VISION_UNAVAILABLE:
            text = (
                "✋ Фото уже получено, но Мира сейчас не может закончить чтение. Попробуй ещё раз немного позже."
                if lang == "ru" else
                "✋ The photo is already received, but Mira cannot finish the reading right now. Please try again later."
            )
        elif error_code == palm_core.CV_UNAVAILABLE:
            text = (
                "✋ Фото принято, но визуальный модуль сейчас недоступен. Переснимать не нужно — попробуй позже."
                if lang == "ru" else
                "✋ The photo was received, but the visual module is unavailable. No reshoot is needed — try later."
            )
        elif error_code == palm_core.MULTIPLE_HANDS:
            text = "✋ В кадре вижу несколько рук. Пришли одну ладонь целиком." if lang == "ru" else "✋ I can see more than one hand. Send one whole palm."
        else:
            text = "✋ В кадре не удалось уверенно найти ладонь. Пришли одну ладонь целиком." if lang == "ru" else "✋ I could not confidently find a hand. Send one whole palm."
        await state.set_state(PalmUpload.photo)
        await message.answer(text, reply_markup=back_menu())
        return

    await status.set(BotStage.SUCCESS)
    observations = result.get("observations") or []
    quality = int(round(float((result.get("image_quality") or {}).get("score") or 0) * 100))
    rows = []
    for item in observations[:4]:
        label = PALM_TOPIC_LABELS.get(str(item.get("topic") or ""), "Наблюдение")
        confidence = int(round(float(item.get("confidence") or 0) * 100))
        rows.append(f"• <b>{label}</b> · {confidence}%\n{item.get('summary') or 'без описания'}")
    prompts = result.get("interpretive_prompts") or []
    reflection = f"\n\n<b>Вопрос к себе</b>\n{prompts[0]}" if prompts else ""
    text = (
        f"✋ <b>Что Мира увидела</b>\nКачество кадра: {quality}%\n\n"
        + ("\n\n".join(rows) or "На фото мало различимых зон — Мира не будет их додумывать.")
        + reflection
        + "\n\n<i>Описание основано только на видимом evidence; это не диагноз и не предсказание.</i>"
    )
    await state.clear()
    await message.answer(text, reply_markup=back_menu())


@router.message(PalmUpload.photo, F.photo)
async def palm_photo(message: Message, state: FSMContext, db):
    buf = BytesIO()
    await message.bot.download(message.photo[-1].file_id, destination=buf)
    await _run(message, state, db, buf.getvalue(), "image/jpeg")


@router.message(PalmUpload.photo, F.document)
async def palm_document(message: Message, state: FSMContext, db):
    document = message.document
    mime = (document.mime_type or "").split(";", 1)[0].lower()
    if mime not in ALLOWED_MIME:
        await message.answer(
            "✋ Я получила файл, но это не изображение ладони.\n\nПришли JPEG, PNG или WebP."
            if not (await users.get(db, message.from_user.id) or {}).get("lang") == "en" else
            "✋ I received a file, but it is not a supported palm image.\n\nSend JPEG, PNG or WebP.",
            reply_markup=back_menu(),
        )
        return
    buf = BytesIO()
    try:
        await message.bot.download(document.file_id, destination=buf)
    except Exception:
        await message.answer("✋ Файл не удалось скачать. Пришли его ещё раз." if mime != "image/jpeg" else "✋ Не удалось скачать изображение. Пришли его ещё раз.", reply_markup=back_menu())
        return
    await _run(message, state, db, buf.getvalue(), mime)


@router.message(PalmUpload.photo, F.text)
async def palm_waiting_text(message: Message):
    await message.answer("✋ Здесь жду фото ладони или image-document: JPEG, PNG или WebP.", reply_markup=back_menu())
