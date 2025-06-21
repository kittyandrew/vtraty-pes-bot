FROM python:3.12
WORKDIR /build

RUN apt-get update \
 && apt-get install -y ffmpeg libsm6 libxext6 wkhtmltopdf git nodejs npm

RUN cd ~ \
 && git clone --single-branch --branch 1.1.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
 && cd bgutil-ytdlp-pot-provider/server/ \
 && npm install -g corepack \
 && yarn install --frozen-lockfile \
 && npx tsc

# Setup: https://github.com/pyppeteer/pyppeteer/issues/108#issuecomment-787150882
RUN curl -sSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
 && echo "deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
 && apt update -y && apt install -y google-chrome-stable

WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip3 install --upgrade pip wheel \
 && pip3 install --no-cache-dir -r requirements.txt

COPY src src
COPY static static
# Launch
ENTRYPOINT ["python3", "-m", "src"]
