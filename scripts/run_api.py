"""Dev-превью API: биндится на порт из env PORT (для preview_start с autoPort).

Пока без него: превью-фреймворк назначает свободный порт через PORT, а uvicorn
в launch.json жёстко пишет --port 8080 — при занятом порту старт падает.
"""
import os
import sys

# при запуске `python scripts/run_api.py` корень репо не попадает в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
    )