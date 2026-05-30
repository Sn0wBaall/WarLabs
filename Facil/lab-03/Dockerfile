FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && \
    apt install -y apache2 php openssh-server sudo nano vim neovim && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash sn0wfl4k3 && \
    echo "sn0wfl4k3:superpass123" | chpasswd

RUN mkdir /var/run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

RUN rm -f /var/www/html/index.html
COPY html /var/www/html
RUN chown -R www-data:www-data /var/www/html

RUN echo "ALL ALL=(root) NOPASSWD: /usr/bin/tar" >> /etc/sudoers

COPY content/mail.txt /var/mail/sn0wfl4k3

COPY content/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80 22

CMD ["/start.sh"]
