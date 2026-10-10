FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y apache2 php libapache2-mod-php nano vim net-tools sudo && \
    rm -rf /var/lib/apt/lists/*

RUN rm -rf /var/www/*
COPY html/ /var/www/html/

# El gestor de archivos escribe en uploads/. Sin este directorio,
# move_uploaded_file() falla en silencio: el upload parece funcionar (302 de
# vuelta al index) pero el archivo no se guarda y no hay RCE posible.
RUN mkdir -p /var/www/html/uploads

RUN chown -R www-data:www-data /var/www/html \
    && chmod 755 /var/www/html

RUN chmod u+s /usr/bin/php

# Flag del lab: solo root puede leerla, hay que escalar privilegios.
COPY content/flag.txt /root/flag.txt
RUN chmod 600 /root/flag.txt

RUN a2enmod php8.1 || true

EXPOSE 80

CMD ["apachectl", "-D", "FOREGROUND"]

