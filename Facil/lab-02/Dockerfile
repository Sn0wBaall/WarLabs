FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y apache2 php libapache2-mod-php nano vim net-tools sudo && \
    rm -rf /var/lib/apt/lists/*

RUN rm -rf /var/www/*
COPY html/ /var/www/html/

RUN chown -R www-data:www-data /var/www/html \
    && chmod 755 /var/www/html

RUN chmod u+s /usr/bin/php

RUN a2enmod php8.1 || true

EXPOSE 80

CMD ["apachectl", "-D", "FOREGROUND"]

