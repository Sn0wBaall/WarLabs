FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/sbin:/usr/sbin:${PATH}"

RUN apt update && \
    apt install -y openssh-server sudo nano vim net-tools openssh-client python3 && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && ssh-keygen -A

RUN useradd -m sn0w && \
    echo "sn0w:sn0w" | chpasswd && \
    chsh -s /bin/bash sn0w

RUN echo 'export PATH=/sbin:/usr/sbin:$PATH' >> /etc/profile

RUN sed -i 's/#LoginGraceTime 2m/LoginGraceTime 2m/' /etc/ssh/sshd_config && \
    sed -i 's/#MaxStartups 10:30:100/MaxStartups 100:30:200/' /etc/ssh/sshd_config && \
    sed -i 's/#MaxAuthTries 6/MaxAuthTries 100/' /etc/ssh/sshd_config

RUN echo "FLAG{CVE_2024_6387_RegreSSHion}" > /root/flag.txt && \
    chmod 600 /root/flag.txt

RUN echo "kernel.randomize_va_space = 0" >> /etc/sysctl.conf

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]
