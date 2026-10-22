FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# root가 아닌 사용자로 실행한다.
RUN useradd --system app
USER app

EXPOSE 8008
CMD ["uvicorn", "transfer_recommender.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8008"]
