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
FROM_CODE = os.environ.get("FROM_CODE", "")  # код станции Экспресс-3, если пусто — ищем по имени
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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "ru-RU,ru;q=0.9"})


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


# ---------- станции ----------

def find_station(name):
    """Ищет код станции по названию через подсказки РЖД."""
    try:
        r = session.get("https://ticket.rzd.ru/api/v1/suggests",
                        params={"Query": name, "TransportType": "rail",
                                "GroupResults": "true", "RailwaySortPriority": "true"},
                        timeout=20)
        r.raise_for_status()
        data = r.json()
        for group in ("city", "train", "avia"):
            for item in data.get(group) or []:
                if item.get("expressCode"):
                    return str(item["expressCode"]), item.get("name", name)
    except Exception as e:
        log("suggests (ticket.rzd.ru) не сработал:", e)
    try:
        r = session.get("https://pass.rzd.ru/suggester",
                        params={"stationNamePart": name.upper(), "lang": "ru", "compactMode": "y"},
                        timeout=20)
        r.raise_for_status()
        items = r.json()
        exact = [i for i in items if i.get("n", "").upper() == name.upper()]
        item = (exact or items)[0]
        return str(item["c"]), item["n"]
    except Exception as e:
        raise SystemExit(f"Не нашёл код станции «{name}»: {e}. Задай его вручную в FROM_CODE/TO_CODE.")


# ---------- поиск поездов ----------
# Нормализованный формат: [{"train", "dep", "arr", "cars": [{"type", "seats", "price"}]}]

def search_ticket_rzd(code0, code1, d):
    body = {
        "Origin": code0, "Destination": code1,
        "DepartureDate": f"{d.isoformat()}T00:00:00",
        "TimeFrom": 0, "TimeTo": 24,
        "CarGrouping": "DontGroup", "GetByLocalTime": True,
        "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons",
        "CarIssuingType": "All", "GetTrainsFromSchedule": True,
    }
    r = session.post("https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/TrainPricing",
                     params={"service_provider": "B2B_RZD"}, json=body, timeout=30)
    r.raise_for_status()
    res = []
    for t in r.json().get("Trains") or []:
        cars = {}
        for g in t.get("CarGroups") or []:
            typ = (g.get("CarTypeName") or g.get("CarType") or "?").upper()
            seats = int(g.get("TotalPlaceQuantity") or g.get("PlaceQuantity") or 0)
            price = g.get("MinPrice")
            c = cars.setdefault(typ, {"type": typ, "seats": 0, "price": None})
            c["seats"] += seats
            if price is not None and (c["price"] is None or price < c["price"]):
                c["price"] = float(price)
        res.append({
            "train": (t.get("DisplayTrainNumber") or t.get("TrainNumber") or "?").upper(),
            "dep": (t.get("LocalDepartureDateTime") or t.get("DepartureDateTime") or "")[:16],
            "arr": (t.get("LocalArrivalDateTime") or t.get("ArrivalDateTime") or "")[:16],
            "cars": list(cars.values()),
        })
    return res


def search_pass_rzd(code0, code1, d):
    url = "https://pass.rzd.ru/timetable/public/ru"
    params = {"layer_id": 5827, "dir": 0, "tfl": 3, "checkSeats": 1,
              "code0": code0, "code1": code1, "dt0": d.strftime("%d.%m.%Y")}
    data = session.get(url, params=params, timeout=30).json()
    for _ in range(10):
        if data.get("result") != "RID":
            break
        time.sleep(1.5)
        data = session.get(url, params={**params, "rid": data.get("RID") or data.get("rid")},
                           timeout=30).json()
    if data.get("result") != "OK":
        raise RuntimeError(f"pass.rzd.ru ответил: {str(data)[:200]}")
    res = []
    for tp in data.get("tp") or []:
        for t in tp.get("list") or []:
            dd = lambda x: datetime.strptime(x, "%d.%m.%Y").date().isoformat()
            res.append({
                "train": t.get("number", "?").upper(),
                "dep": f"{dd(t['date0'])}T{t['time0']}" if t.get("date0") else "",
                "arr": f"{dd(t['date1'])}T{t['time1']}" if t.get("date1") else "",
                "cars": [{"type": (c.get("typeLoc") or c.get("type") or "?").upper(),
                          "seats": int(c.get("freeSeats") or 0),
                          "price": float(c["tariff"]) if c.get("tariff") else None}
                         for c in t.get("cars") or []],
            })
    return res


def search(code0, code1, d):
    try:
        return search_ticket_rzd(code0, code1, d)
    except Exception as e:
        log(f"ticket.rzd.ru ошибка ({e}), пробую pass.rzd.ru")
        return search_pass_rzd(code0, code1, d)


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


def buy_link(code0, code1, d):
    return f"https://ticket.rzd.ru/searchresults/v/1/{code0}/{code1}/{d.isoformat()}"


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
