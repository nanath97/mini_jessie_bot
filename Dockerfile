FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    supervisor \
    default-jre-headless \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY Bridge/package*.json ./Bridge/

RUN cd Bridge && npm install --omit=dev

COPY verapdf-install.xml /tmp/verapdf-install.xml

RUN python -c "import urllib.request; urllib.request.urlretrieve('https://software.verapdf.org/rel/1.30/verapdf-greenfield-1.30.2-installer.zip','/tmp/verapdf.zip')" \
    && python -c "import zipfile; zipfile.ZipFile('/tmp/verapdf.zip').extractall('/tmp/verapdf-installer')" \
    && chmod +x /tmp/verapdf-installer/verapdf-greenfield-1.30.2/verapdf-install \
    && /tmp/verapdf-installer/verapdf-greenfield-1.30.2/verapdf-install /tmp/verapdf-install.xml \
    && ln -s /opt/verapdf/verapdf /usr/local/bin/verapdf \
    && rm -rf /tmp/verapdf.zip /tmp/verapdf-installer /tmp/verapdf-install.xml

COPY . .

ENV FACTURX_VERAPDF=/usr/local/bin/verapdf

EXPOSE 10000

CMD ["supervisord", "-c", "/app/supervisord.conf"]