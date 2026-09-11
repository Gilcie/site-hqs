FROM python:3.12-slim

# unrar (non-free component) — used for CBR (RAR) extraction. 7-Zip's own
# RAR codec ("p7zip-full") fails with "Unsupported Method" on a lot of
# older/nonstandard RAR compression methods that the official unrar reads fine.
RUN sed -i 's/Components: main/Components: main non-free non-free-firmware contrib/' /etc/apt/sources.list.d/*.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends unrar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
# mega.py pins an old tenacity that breaks on Python 3.12 (asyncio.coroutine
# was removed). Upgrading it separately avoids pip's resolver backtracking
# into an ancient mega.py release that depends on the unmaintained "pycrypto"
# package (which needs a C compiler to build).
RUN pip install --no-cache-dir -U tenacity

COPY . .

RUN mkdir -p /app/comics /app/cache

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "120", "app:app"]
