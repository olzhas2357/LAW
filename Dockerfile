FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY scripts ./scripts
COPY legal_bot.json legal_bot_en.json legal_bot_ru.json ./

RUN mkdir -p /app/cache
CMD ["python", "-m", "bot.main"]
