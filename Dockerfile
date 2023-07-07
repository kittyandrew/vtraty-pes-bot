FROM python:3.10-slim-buster

WORKDIR /usr/src/app

COPY requirements.txt .
RUN pip3 install --upgrade pip wheel \
 && pip3 install --no-cache-dir -r requirements.txt

COPY src src
# Launch
ENTRYPOINT ["python3", "-m", "src"]
