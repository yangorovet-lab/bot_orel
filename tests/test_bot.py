"""Офлайн-тесты логики бота: парсинг ответа РЖД, фильтры, антиспам."""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_resp(seats_coupe=3, seats_plats=9):
    return {"Trains": [{
        "TrainNumber": "742В",
        "LocalDepartureDateTime": "2099-01-01T07:10:00",
        "LocalArrivalDateTime": "2099-01-01T10:40:00",
        "CarGroups": [
            {"CarTypeName": "Купе", "PlaceQuantity": seats_coupe, "MinPrice": 2100},
            {"CarTypeName": "Плацкартный", "PlaceQuantity": seats_plats, "MinPrice": 900},
        ],
    }]}


class FakeResp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.update(STATE_FILE=os.path.join(self.tmp, "st.json"), DATES="2099-01-01",
                          CAR_TYPES="КУПЕ,СВ", TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
        import bot
        self.bot = importlib.reload(bot)
        self.bot.time.sleep = lambda s: None
        self.resp = make_resp()
        self.bot.session.post = lambda *a, **k: FakeResp(self.resp)
        self.sent = []
        self.bot.send_tg = self.sent.append

    def check(self):
        self.bot.check_once("2000140", "2000000")

    def test_default_station_codes(self):
        self.assertEqual(self.bot.FROM_CODE, "2000140")
        self.assertEqual(self.bot.TO_CODE, "2000000")

    def test_parse_and_filter(self):
        trains = self.bot.search_ticket_rzd("2000140", "2000000", self.bot.date(2099, 1, 1))
        self.assertEqual(trains[0]["train"], "742В")
        cars = self.bot.matching_cars(trains[0])
        self.assertEqual([c["type"] for c in cars], ["КУПЕ"])  # плацкарт отфильтрован

    def test_notifies_once_with_link(self):
        self.check()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("742В", self.sent[0])
        self.assertIn("https://ticket.rzd.ru/searchresults/v/1/2000140/2000000/2099-01-01", self.sent[0])
        self.check()
        self.assertEqual(len(self.sent), 1, "повторно о тех же местах не пишем")

    def test_notifies_again_after_seats_return(self):
        self.check()
        self.resp = make_resp(seats_coupe=0)
        self.check()
        self.resp = make_resp(seats_coupe=2)
        self.check()
        self.assertEqual(len(self.sent), 2)

    def test_max_price_filter(self):
        self.bot.MAX_PRICE = 1000
        self.check()
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
