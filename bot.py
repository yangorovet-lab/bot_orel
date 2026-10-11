#!/usr/bin/env python3
"""Ловит свободные места на поезда Орёл -> Москва (РЖД) и шлёт уведомления в Telegram."""
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests


def load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
FROM_NAME = os.environ.get("FROM_STATION", "ОРЕЛ")
TO_NAME = os.environ.get("TO_STATION", "МОСКВА")
FROM_CODE = os.environ.get("FROM_CODE", "2000140")  # Орёл; если пусто — ищем по имени
TO_CODE = os.environ.get("TO_CODE", "2000000")  # 2000000 = Москва (все вокзалы)
DATES = os.environ.get("DATES", "")  # 2026-10-15,2026-10-16 или пусто = ближайшие DAYS_AHEAD дней
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "3"))
TRAINS = [t.strip().upper() for t in os.environ.get("TRAINS", "").split(",") if t.strip()]
CAR_TYPES = [t.strip().upper() for t in os.environ.get("CAR_TYPES", "").split(",") if t.strip()]
MAX_PRICE = float(os.environ.get("MAX_PRICE", "0") or 0)
TIME_FROM = os.environ.get("TIME_FROM", "00:00")
TIME_TO = os.environ.get("TIME_TO", "23:59")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "5"))
INTERVAL_MAX = int(os.environ.get("INTERVAL_MAX", "10"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))

def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


from rzd import buy_link, find_station, search, search_pass_rzd, search_ticket_rzd, session  # noqa: E402,F401


# ---------- фильтры и уведомления ----------

def in_window(dep):
    hm = dep[11:16]
    return not hm or TIME_FROM <= hm <= TIME_TO


def matching_cars(train):
    if TRAINS and not any(train["train"].startswith(n) for n in TRAINS):
        return []
    if not in_window(train["dep"]):
        return []
    out = []
    for c in train["cars"]:
        if c["seats"] <= 0:
            continue
        if CAR_TYPES and not any(ct in c["type"] for ct in CAR_TYPES):
            continue
        if MAX_PRICE and c["price"] and c["price"] > MAX_PRICE:
            continue
        out.append(c)
    return out


def send_tg(text):
    if not TG_TOKEN or not TG_CHAT:
        log("TELEGRAM_* не заданы, сообщение:\n" + text)
        return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=20)
    if not r.ok:
        log("Telegram ошибка:", r.status_code, r.text[:200])


def target_dates():
    if DATES:
        ds = [date.fromisoformat(x.strip()) for x in DATES.split(",") if x.strip()]
    else:
        ds = [date.today() + timedelta(days=i) for i in range(DAYS_AHEAD)]
    return [d for d in ds if d >= date.today()]


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def check_once(code0, code1):
    state = load_state()
    new_state = {}
    for d in target_dates():
        try:
            trains = search(code0, code1, d)
        except Exception as e:
            log(f"{d}: не удалось получить поезда: {e}")
            # не теряем прошлое состояние этой даты, чтобы не заспамить после сбоя
            new_state.update({k: v for k, v in state.items() if k.startswith(d.isoformat())})
            continue
        lines = []
        for t in trains:
            for c in matching_cars(t):
                key = f"{d.isoformat()}|{t['train']}|{c['type']}"
                new_state[key] = c["seats"]
                if key not in state:  # места появились (раньше их не было)
                    price = f", от {c['price']:.0f} ₽" if c["price"] else ""
                    lines.append(f"🚆 <b>{t['train']}</b> {t['dep'][11:16]} → {t['arr'][11:16]} · "
                                 f"{c['type'].lower()}: {c['seats']} мест{price}")
        log(f"{d}: поездов {len(trains)}, новых вариантов {len(lines)}")
        if lines:
            send_tg(f"🎫 Появились билеты {FROM_NAME.title()} → {TO_NAME.title()} на "
                    f"<b>{d.strftime('%d.%m.%Y')}</b>\n\n" + "\n".join(lines) +
                    f"\n\n👉 <a href=\"{buy_link(code0, code1, d)}\">Купить на ticket.rzd.ru</a>")
        time.sleep(random.uniform(1, 3))
    STATE_FILE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    code0 = FROM_CODE or find_station(FROM_NAME)[0]
    code1 = TO_CODE or find_station(TO_NAME)[0]
    log(f"Маршрут {FROM_NAME} ({code0}) → {TO_NAME} ({code1}), даты: "
        f"{', '.join(d.isoformat() for d in target_dates())}")
    if "--once" in sys.argv:
        check_once(code0, code1)
        return
    if "--test" in sys.argv:
        send_tg("✅ Бот билетов Орёл → Москва подключён")
    while True:
        try:
            check_once(code0, code1)
        except Exception as e:
            log("Ошибка проверки:", e)
        pause = random.randint(INTERVAL_MIN * 60, INTERVAL_MAX * 60)
        log(f"Следующая проверка через {pause // 60} мин {pause % 60} с")
        time.sleep(pause)


if __name__ == "__main__":
    main()
