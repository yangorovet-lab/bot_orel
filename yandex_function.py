"""Обработчик для Yandex Cloud Functions (точка входа: yandex_function.handler).

У функций Yandex Cloud российский IP, поэтому РЖД им отвечает. Лендинг на GitHub Pages
обращается к URL функции: ?from=2000140&to=2000000&date=ГГГГ-ММ-ДД
"""
import json

import rzd

HEADERS = {"Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*"}


def handler(event, context):
    q = (event or {}).get("queryStringParameters") or {}
    try:
        code, body = 200, rzd.trains_payload(q.get("from"), q.get("to"), q.get("date"))
    except ValueError as e:
        code, body = 400, {"error": str(e)}
    except Exception as e:
        print("РЖД:", repr(e))
        code, body = 502, {"error": "РЖД не ответил, попробуйте через минуту"}
    return {"statusCode": code, "headers": HEADERS, "body": json.dumps(body, ensure_ascii=False)}
