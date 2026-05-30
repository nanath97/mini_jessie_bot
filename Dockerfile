FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Bridge/package*.json ./Bridge/
RUN cd Bridge && npm install --omit=dev

COPY . .

EXPOSE 10000

CMD ["supervisord", "-c", "/app/supervisord.conf"]