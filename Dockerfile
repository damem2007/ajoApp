FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . /app
RUN python -m pip install --upgrade pip && python -m pip install .

RUN useradd --create-home --uid 10001 ajo && chown -R ajo:ajo /app
USER ajo

EXPOSE 9020
CMD ["python","-m","uvicorn","app.platform.application:app","--host","0.0.0.0","--port","9020"]
