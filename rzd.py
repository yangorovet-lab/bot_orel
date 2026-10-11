"""Запросы к РЖД: поиск станций и поездов со свободными местами. Общий код для бота и сервера."""
import time
from datetime import date, datetime, timedelta

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "ru-RU,ru;q=0.9"})


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
        print("suggests (ticket.rzd.ru) не сработал:", e, flush=True)
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
        raise RuntimeError(f"Не нашёл код станции «{name}»: {e}. Задай его вручную в FROM_CODE/TO_CODE.")


# ---------- поиск поездов ----------

def is_real_seats(group, seats):
    """Места, которые можно купить прямо сейчас. Лист ожидания и закрытая продажа не считаются."""
    if seats <= 0:
        return False
    avail = group.get("AvailabilityIndication")
    return not avail or avail == "Available"

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
            if not is_real_seats(g, seats):
                continue
            price = g.get("MinPrice")
            c = cars.setdefault(typ, {"type": typ, "seats": 0, "price": None})
            c["seats"] += seats
            if price is not None and (c["price"] is None or price < c["price"]):
                c["price"] = float(price)
        res.append({
            "train": (t.get("DisplayTrainNumber") or t.get("TrainNumber") or "?").upper(),
            "name": (t.get("TrainName") or t.get("TrainBrandCode") or "").strip(),
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
                "name": (t.get("brand") or "").strip(),
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
        print(f"ticket.rzd.ru ошибка ({e}), пробую pass.rzd.ru", flush=True)
        return search_pass_rzd(code0, code1, d)


def buy_link(code0, code1, d):
    return f"https://ticket.rzd.ru/searchresults/v/1/{code0}/{code1}/{d.isoformat()}"


def free_only(trains):
    """Только поезда, где есть хотя бы один тип вагона с реальными местами."""
    out = []
    for t in trains:
        cars = [c for c in t["cars"] if c["seats"] > 0]
        if cars:
            out.append({**t, "cars": sorted(cars, key=lambda c: (c["price"] is None, c["price"] or 0))})
    return sorted(out, key=lambda t: t["dep"])


ALLOWED_STATIONS = {"2000140": "Орёл", "2000000": "Москва"}
MAX_DAYS_AHEAD = 120


def trains_payload(frm, to, day, today=None):
    """Ответ API /api/trains. Разрешены только станции из ALLOWED_STATIONS, чтобы сервер не был открытым прокси."""
    if frm not in ALLOWED_STATIONS or to not in ALLOWED_STATIONS or frm == to:
        raise ValueError("Неизвестная станция")
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        raise ValueError("Дата должна быть в формате ГГГГ-ММ-ДД")
    today = today or date.today()
    if not today <= d <= today + timedelta(days=MAX_DAYS_AHEAD):
        raise ValueError("Дата вне диапазона продажи билетов")
    return {
        "from": frm, "to": to, "date": d.isoformat(),
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "buy_url": buy_link(frm, to, d),
        "trains": free_only(search(frm, to, d)),
    }
