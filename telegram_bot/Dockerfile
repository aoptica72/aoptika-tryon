FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY telegram_bot/requirements.txt /app/telegram_bot/requirements.txt
RUN pip install --no-cache-dir -r /app/telegram_bot/requirements.txt
COPY . /app
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser
CMD ["python", "-m", "telegram_bot.app"]