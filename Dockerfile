FROM --platform=linux/amd64 python:3.11-slim

# System deps for Chrome
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    libxss1 libgbm1 xdg-utils --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O /tmp/chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
# Tell the app to run headless
ENV HIRINGFUNNEL_HEADLESS=1

# --run requires a profile name; users pass it via env or override CMD
CMD ["python", "hiringfunnel.py", "--run", "default", "--headless"]