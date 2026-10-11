# Билеты Орёл → Москва: ловец свободных мест

## Сайт со свободными местами
Страница показывает поезда Орёл ⇄ Москва, где места можно купить прямо сейчас (без листа ожидания).
По клику на поезд открывается поиск РЖД на эту дату.

Как устроено:
- `landing/index.html` — страница. Места она берёт у API по адресу `API_URL`.
- `rzd.py` — запросы к РЖД и фильтр: показываем только группы вагонов, где мест больше нуля и продажа открыта.
- `server.py` — сайт и API `/api/trains?from=2000140&to=2000000&date=ГГГГ-ММ-ДД` в одном. Кэш 60 секунд,
  разрешены только Орёл и Москва, поэтому чужим прокси к РЖД сервер стать не может.
- `yandex_function.py` — то же API в виде функции Yandex Cloud.

**API должен работать с российского IP.** РЖД не отвечает зарубежным серверам: GitHub Actions проверял это 11.10.2026.

### Вариант А: свой сервер или VPS в России (всё в одном)
```bash
pip install -r requirements.txt
python server.py 8080        # открой http://адрес-сервера:8080/
# или: docker build -t orel-tickets . && docker run -d --restart=always -p 8080:8080 orel-tickets
```

### Вариант Б: страница на GitHub Pages + бесплатная функция Yandex Cloud
1. В [Yandex Cloud](https://console.yandex.cloud) создай Cloud Functions → «Создать функцию», отметь «Публичная».
2. Редактор: среда **Python 3.12**, способ — ZIP-архив из файлов `rzd.py`, `yandex_function.py`, `requirements.txt`.
   Точка входа: `yandex_function.handler`, таймаут 30 с, память 128 МБ.
3. Скопируй ссылку вызова функции (`https://functions.yandexcloud.net/...`).
4. В GitHub: Settings → Secrets and variables → Actions → Variables → `API_URL` = эта ссылка.
5. Actions → deploy-landing → Run workflow. Сайт: **https://yangorovet-lab.github.io/bot_orel/**

Пока `API_URL` не задан, на GitHub Pages страница показывает «Не получилось загрузить места» и кнопку на РЖД.

### Тесты
`python -m unittest discover -s tests` (бот, API, сервер) и `npm install && npm test` (страница в Chromium, API подменён).
Workflow `tests` гоняет оба набора на каждый push, плюс живую проверку РЖД с серверов GitHub.

---

Скрипт раз в 5–10 минут проверяет поезда РЖД из Орла в Москву на нужные даты. Когда появляются свободные места, он шлёт в Telegram сообщение: поезд, время, тип вагона, сколько мест, цена и ссылка на покупку.

## 1. Telegram-бот (2 минуты)
1. Напиши [@BotFather](https://t.me/BotFather), выполни `/newbot` и получи **токен**.
2. Напиши своему новому боту что угодно, иначе он не сможет тебе писать.
3. Узнай свой **chat id** у [@userinfobot](https://t.me/userinfobot).

## 2. Запуск (лучше с российского IP: дома или на VPS в РФ)
РЖД часто блокирует зарубежные IP, поэтому надёжнее всего запускать на своём компьютере или на дешёвом российском VPS.

```bash
pip install -r requirements.txt
cp .env.example .env      # впиши токен, chat id и даты
python bot.py --test      # пришлёт тестовое сообщение и начнёт следить
```

Через Docker:
```bash
docker build -t orel-tickets .
docker run -d --restart=always --env-file .env -v $PWD/data:/app/data orel-tickets
```

## 3. Вариант без сервера: GitHub Actions
Workflow `.github/workflows/check.yml` запускает проверку по крону `*/5`. По умолчанию он выключен: включи переменную `ENABLE_CHECK=true`.
- Settings → Secrets → Actions: добавь `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.
- Settings → Variables: `DATES` (например `2026-10-17,2026-10-18`), при желании `CAR_TYPES`, `TRAINS`, `MAX_PRICE`.

⚠️ Проверено 11.10.2026: РЖД не отвечает серверам GitHub (соединение обрывается по таймауту). Пока это так, вариант с GitHub Actions работать не будет. Используй вариант 2 с российского IP.

## Настройки (`.env`)
| Переменная | Что делает |
|---|---|
| `DATES` | даты через запятую; если пусто, ближайшие `DAYS_AHEAD` дней |
| `CAR_TYPES` | `ПЛАЦ`, `КУПЕ`, `СВ`, `СИД`, … |
| `TRAINS` | только эти номера поездов |
| `MAX_PRICE` | максимальная цена |
| `TIME_FROM` / `TIME_TO` | окно отправления, например `06:00`–`20:00` |
| `INTERVAL_MIN` / `INTERVAL_MAX` | пауза между проверками, в минутах |
| `FROM_CODE` / `TO_CODE` | коды станций, если автопоиск по названию не сработал |

Повторно бот пишет только тогда, когда места пропали и появились снова.
