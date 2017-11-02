FROM debian:jessie
RUN apt-get update \
    && apt-get install -y apt-transport-https ca-certificates \
    && apt-get clean \
    && rm -rf /var/cache/apt/*
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python-pip python-dev \
    && apt-get clean && rm -rf /var/cache/apt/*

RUN pip install -U setuptools
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

WORKDIR /app

COPY docker/init.sh /init.sh
CMD ["/init.sh"]
