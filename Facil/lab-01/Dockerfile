FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/sbin:/usr/sbin:${PATH}" 

RUN apt update && \
    apt install -y openssh-server vim nano apache2 sudo libcap2-bin python3 && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && ssh-keygen -A
RUN setcap cap_setuid+ep /usr/bin/python3.11

RUN useradd -m cody && \
  echo "cody:asdfghjkl" | chpasswd

RUN chsh -s /bin/bash cody
RUN echo 'export PATH=/sbin:/usr/sbin:$PATH' >> /etc/profile

RUN rm -rf /var/www/html
COPY html /var/www/html

RUN sed -i 's/#MaxStartups 10:30:100/MaxStartups 100:30:200/' /etc/ssh/sshd_config

EXPOSE 22 80

CMD service apache2 start && /usr/sbin/sshd -D
