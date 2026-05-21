FROM python:3.12-slim

WORKDIR /app

COPY packaging/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt flask requests rich

COPY . .

EXPOSE 7860

ENV MISER_PORT=7860
ENV MISER_LOG_FORMAT=json

CMD ["python3", "miser.py"]
