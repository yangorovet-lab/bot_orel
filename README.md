# Билеты Орёл → Москва: ловец свободных мест

## Лендинг
`landing/index.html` — страница быстрого поиска: выбираешь дату, и она открывает поиск РЖД с готовым маршрутом.
Публикуется на GitHub Pages workflow-ом `deploy-landing`: **https://yangorovet-lab.github.io/bot_orel/**
(один раз включи Settings → Pages → Source: **GitHub Actions**).

Тесты: `python -m unittest discover -s tests` (бот) и `npm install && npm test` (лендинг в Chromium).
Workflow `tests` на каждый push гоняет оба набора и живую проверку РЖД с серверов GitHub.

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

⚠️ Серверы GitHub стоят за границей, и РЖД может их не пускать. Посмотри логи первого запуска (Actions → Run workflow). Если видишь ошибки подключения, используй вариант 2.

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
