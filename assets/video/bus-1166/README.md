# BUS-1166: ffmpeg-оверлеи для 4 видео

## Pipeline

```
assets/video/bus-1166/
├── raw/          ← BUS-1209 положит 4 MP4 сюда
│   ├── oracle.mp4
│   ├── astro.mp4
│   ├── tarot.mp4
│   └── chiromant.mp4
├── final/        ← результат ffmpeg-скрипта
│   ├── oracle.mp4
│   ├── astro.mp4
│   ├── tarot.mp4
│   └── chiromant.mp4
└── scratch/      ← временные PNG-оверлеи (gitignored)
```

## Быстрый старт (когда raw MP4 готовы)

```bash
# 1. Проверка наличия raw-файлов
ls assets/video/bus-1166/raw/*.mp4

# 2. Запуск батча на все 4 агента
bash scripts/bus1175_batch.sh

# 3. Верификация каждого final-файла
python scripts/bus1175_video_overlays.py verify \
    assets/video/bus-1166/final/oracle.mp4 \
    --raw assets/video/bus-1166/raw/oracle.mp4 \
    --agent oracle
```

## Субтитры per-агент

| Агент | Л1 | Л2 | Л3 |
|---|---|---|---|
| oracle | _заполнить_ | _заполнить_ | _заполнить_ |
| astro | _заполнить_ | _заполнить_ | _заполнить_ |
| tarot | _заполнить_ | _заполнить_ | _заполнить_ |
| chiromant | _заполнить_ | _заполнить_ | _заполнить_ |

> Текст субтитров — зона UX/UI Designer (BUS-1166 spec §2.4).

## Acceptance (BUS-1175 спека)

- [ ] 4 final MP4 1080×1920, 11.5–12с
- [ ] Субтитры: 3 окна 2.0–5.5 / 5.5–9.0 / 9.0–11.5, backdrop rgba(0,0,0,0.45)
- [ ] CTA: 9–12с, pill 64px height, accent per-agent
- [ ] Дисклеймер: весь кадр, y 1780–1840
- [ ] Шрифт Manrope full (не subset-woff2)
- [ ] ffprobe-отчёт в комментарии
- [ ] Чек-лист BUS-1175 заполнен
