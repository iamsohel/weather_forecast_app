FROM python:3.11-alpine

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install application dependencies
COPY ./requirements.txt /requirements.txt

RUN pip install --upgrade pip

RUN apk update && apk add bash
RUN apk add --update --no-cache --virtual .tmp-build-deps \
      gcc libc-dev linux-headers
RUN pip install -r /requirements.txt
RUN apk del .tmp-build-deps

# copy project
COPY . .

EXPOSE 8000