FROM python:3.12

WORKDIR /usr/src/app

RUN apt-get update \
 && apt-get install ffmpeg libsm6 libxext6 wkhtmltopdf -y \
 # Setup: https://github.com/pyppeteer/pyppeteer/issues/108#issuecomment-787150882 \
 && curl -sSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
 && echo "deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
 && apt update -y && apt install -y google-chrome-stable ffmpeg

COPY requirements.txt .
RUN pip3 install --upgrade pip wheel \
 && pip3 install --no-cache-dir -r requirements.txt

COPY src src
COPY static static
# Launch
ENTRYPOINT ["python3", "-m", "src"]
