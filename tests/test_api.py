"""Офлайн-тесты API свободных мест: фильтр листа ожидания, валидация, сервер, функция Yandex Cloud."""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rzd  # noqa: E402

TOMORROW = (date.today() + timedelta(days=1)).isoformat()

RZD_RESPONSE = {"Trains": [
    {"TrainNumber": "742В", "TrainName": "Ласточка",
     "LocalDepartureDateTime": f"{TOMORROW}T07:10:00", "LocalArrivalDateTime": f"{TOMORROW}T10:40:00",
     "CarGroups": [
         {"CarTypeName": "Сидячий", "PlaceQuantity": 14, "MinPrice": 1450, "AvailabilityIndication": "Available"},
         {"CarTypeName": "Сидячий", "PlaceQuantity": 3, "MinPrice": 1300, "AvailabilityIndication": "Available"},
     ]},
    # лист ожидания: мест 0
    {"TrainNumber": "034М", "LocalDepartureDateTime": f"{TOMORROW}T05:00:00",
     "LocalArrivalDateTime": f"{TOMORROW}T09:30:00",
     "CarGroups": [{"CarTypeName": "Купе", "PlaceQuantity": 0, "MinPrice": 3000}]},
    # места есть, но продажа в вебе закрыта
    {"TrainNumber": "072", "LocalDepartureDateTime": f"{TOMORROW}T23:00:00",
     "LocalArrivalDateTime": f"{TOMORROW}T23:59:00",
     "CarGroups": [{"CarTypeName": "СВ", "PlaceQuantity": 4, "MinPrice": 7000,
                    "AvailabilityIndication": "NotAvailableInWeb"}]},
    {"TrainNumber": "016А", "LocalDepartureDateTime": f"{TOMORROW}T01:20:00",
     "LocalArrivalDateTime": f"{TOMORROW}T06:05:00",
     "CarGroups": [{"CarTypeName": "Купе", "PlaceQuantity": 2, "MinPrice": 3200},
                   {"CarTypeName": "Плацкартный", "PlaceQuantity": 0, "MinPrice": 1800}]},
]}


class FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return RZD_RESPONSE


class PayloadTest(unittest.TestCase):
    def setUp(self):
        self.calls = 0

        def post(*a, **k):
            self.calls += 1
            return FakeResp()
        rzd.session.post = post

    def test_only_real_free_seats(self):
        data = rzd.trains_payload("2000140", "2000000", TOMORROW)
        trains = {t["train"]: t for t in data["trains"]}
        self.assertEqual(list(trains), ["016А", "742В"], "отсортировано по времени, без листа ожидания")
        self.assertEqual(trains["742В"]["cars"], [{"type": "СИДЯЧИЙ", "seats": 17, "price": 1300.0}])
        self.assertEqual(trains["742В"]["name"], "Ласточка")
        self.assertEqual([c["type"] for c in trains["016А"]["cars"]], ["КУПЕ"])
        self.assertEqual(data["buy_url"], f"https://ticket.rzd.ru/searchresults/v/1/2000140/2000000/{TOMORROW}")

    def test_validation(self):
        for frm, to, day in [("2000140", "2004000", TOMORROW), ("2000140", "2000140", TOMORROW),
                             ("2000140", "2000000", "завтра"), ("2000140", "2000000", "2000-01-01"),
                             ("2000140", "2000000", (date.today() + timedelta(days=400)).isoformat())]:
            with self.assertRaises(ValueError):
                rzd.trains_payload(frm, to, day)
        self.assertEqual(self.calls, 0, "к РЖД не ходим с неправильными параметрами")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        from http.server import ThreadingHTTPServer
        rzd.session.post = lambda *a, **k: FakeResp()
        server.Handler.page = b"<title>test</title>"
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            r = opener.open(self.base + path, timeout=5)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_api(self):
        code, headers, body = self.get(f"/api/trains?from=2000140&to=2000000&date={TOMORROW}")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(len(json.loads(body)["trains"]), 2)

    def test_bad_request(self):
        code, _, body = self.get("/api/trains?from=1&to=2&date=x")
        self.assertEqual(code, 400)
        self.assertIn("error", json.loads(body))

    def test_rzd_down(self):
        import server
        server._cache.clear()

        def boom(*a, **k):
            raise ConnectionError("timeout")
        orig_get = rzd.session.get
        rzd.session.post = rzd.session.get = boom
        try:
            code, _, body = self.get(f"/api/trains?from=2000000&to=2000140&date={TOMORROW}")
            self.assertEqual(code, 502)
        finally:
            rzd.session.get = orig_get
            rzd.session.post = lambda *a, **k: FakeResp()

    def test_page(self):
        code, _, body = self.get("/")
        self.assertEqual((code, body), (200, b"<title>test</title>"))


class YandexFunctionTest(unittest.TestCase):
    def test_handler(self):
        import yandex_function
        rzd.session.post = lambda *a, **k: FakeResp()
        res = yandex_function.handler({"queryStringParameters": {
            "from": "2000140", "to": "2000000", "date": TOMORROW}}, None)
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(res["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertEqual(len(json.loads(res["body"])["trains"]), 2)
        self.assertEqual(yandex_function.handler({}, None)["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
