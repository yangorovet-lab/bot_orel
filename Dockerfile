FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /app/data
ENV STATE_FILE=/app/data/state.json PORT=8080
EXPOSE 8080
# по умолчанию сайт со свободными местами; для Telegram-бота: docker run ... python -u bot.py
CMD ["python", "-u", "server.py"]
