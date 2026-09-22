FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chess_trainer/ chess_trainer/
COPY static/ static/
COPY scripts/ scripts/

ENV DB_PATH=/data/chess_trainer.db
ENV STOCKFISH_PATH=/usr/games/stockfish
VOLUME /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["sh", "-c", "python scripts/init_db.py && uvicorn chess_trainer.api:app --host 0.0.0.0 --port 8000"]
