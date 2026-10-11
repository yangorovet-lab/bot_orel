FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
VOLUME /app/data
ENV STATE_FILE=/app/data/state.json
CMD ["python", "-u", "bot.py"]
