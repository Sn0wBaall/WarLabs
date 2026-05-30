#!/bin/bash

# --- Colors ---
endColor="\033[0m\e[0m"
redColor="\e[0;31m"
blueColor="\e[0;34m"
yellowColor="\e[0;33m"
purpleColor="\e[0;35m"
turquoiseColor="\e[0;36m"
grayColor="\e[0;37m"

BgreenColor="\e[1;32m"
BendColor="\033[0m\e[0m"
BredColor="\e[1;31m"
BblueColor="\e[1;34m"
ByellowColor="\e[1;33m"
BpurpleColor="\e[1;35m"
BturquoiseColor="\e[1;36m"
BgrayColor="\e[1;37m"
# --- Colors ---

banner(){
  echo -e "${BpurpleColor}"
  cat << "EOF"
  ▄▄▄                      ▄▄▄                      
 █▀██  ██  ██▀▀           ▀██▀           █▄         
   ██  ██  ██       ▄      ██            ██         
   ██  ██  ██ ▄▀▀█▄ ████▄  ██      ▄▀▀█▄ ████▄ ▄██▀█
   ██▄ ██▄ ██ ▄█▀██ ██     ██      ▄█▀██ ██ ██ ▀███▄
   ▀████▀███▀▄▀█▄██▄█▀    ████████▄▀█▄██▄████▀█▄▄██▀
EOF
  echo -e "${endColor}"
}                                                                
                                                                          

if [ "$(id -u)" != 0 ]; then
  banner
  echo -e "\n${BredColor}[!]${endColor}${grayColor} Ejecutalo con root${endColor}\n"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1;then
  sudo apt install docker.io
fi

lab_name=$(pwd | awk -F "/" '{print $NF}')
image_name="WarLabs/ssh-lab"
ssh_port="22"
web_port="80"
lab_ip=$(ip -o -4 addr show wlan0 | awk '{print $4}' | cut -d/ -f1)

banner

function ctrl_c(){
  echo -e "${BredColor}[!]${endColor} Saliendo"
}

trap ctrl_c SIGINT

[ -t 1 ] && tput civis

if command -v rmDocker >/dev/null 2>&1; then
  rmDocker
fi

echo -e "\n${ByellowColor}[!]${endColor}${grayColor} Construyendo laboratorio${endColor}${BpurpleColor} ${lab_name}${endColor}"

if ! docker build -t ${image_name} . >/dev/null 2>&1; then
  echo -e "\n${BredColor}[!]${endColor}${grayColor} Error al construir la imagen${endColor}\n"
  [ -t 1 ] && tput cnorm
  exit 1
fi

docker run -d \
  --name ${lab_name} \
  -p ${ssh_port}:22 \
  -p ${web_port}:80 \
  ${image_name} >/dev/null 2>&1

echo -e "\n${BgreenColor}[+]${endColor}${grayColor} Laboratorio${endColor}${BpurpleColor} ${lab_name}${endColor}${grayColor} construido${endColor}"
echo -e "\n${ByellowColor}[i]${endColor}${grayColor} Esta es la IP de el laboratorio${endColor}${BturquoiseColor} -->${endColor}${BpurpleColor} ${lab_ip}${endColor}"
echo -e "${ByellowColor}[i]${endColor}${grayColor} Para eliminar el laboratorio ejecuta${endColor}${BturquoiseColor} -->${endColor}${BpurpleColor} rmDocker${endColor}\n"

[ -t 1 ] && tput cnorm
