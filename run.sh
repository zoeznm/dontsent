#!/bin/bash

if [ ! -d "/mnt/data/root" ]; then
    mkdir -p /mnt/data/root
    cp -a /root/. /mnt/data/root
fi
rm -rf /root
ln -s /mnt/data/root /root

source /root/.bashrc

if [ ! -d "/opt/conda/envs_org" ] && [ ! -L "/opt/conda/envs" ]; then
    mv /opt/conda/envs /opt/conda/envs_org
fi

mkdir -p /mnt/data/data /mnt/data/envs
rm -rf /opt/app/data /opt/conda/envs
ln -s /mnt/data/data /opt/app/data
ln -s /mnt/data/envs /opt/conda/envs

mkdir -p /opt/tmp
mkdir -p /mnt/data/wiz/config /mnt/data/wiz/project /mnt/data/wiz/.github /mnt/data/wiz/log

# project settings
if [ ! -L "/opt/app/config" ]; then
    mv /opt/app/config /opt/tmp/config
fi

rm -rf /opt/app/config /opt/app/project /opt/app/.github /var/log/wiz
ln -s /mnt/data/wiz/config /opt/app/config
ln -s /mnt/data/wiz/project /opt/app/project
ln -s /mnt/data/wiz/.github /opt/app/.github
ln -s /mnt/data/wiz/log /var/log/wiz

if [ ! -d "/opt/conda/envs/app" ]; then
    cp -r /opt/conda/envs_org/app /opt/conda/envs/app
fi

if [ ! -d "/opt/app/.github/.git" ]; then
    git clone https://git.sio.season.co.kr/oss/wiz-copilot-instructions /opt/tmp/.github
    cp -r /opt/tmp/.github/. /opt/app/.github
fi

if [ ! -d "/opt/app/project/main" ]; then
    git clone https://github.com/season-framework/wiz-sample-project /opt/app/project/main
fi

if [ ! -f "/opt/app/config/boot.py" ]; then
    cp -r /opt/tmp/config/* /opt/app/config
fi

rm -rf /opt/tmp

# Setup SSH Password from Environment Variable
if [ ! -z "$SSH_PASSWORD" ]; then
    echo "root:$SSH_PASSWORD" | chpasswd
fi

service ssh restart

pip install -U season pymysql cryptography

wiz service regist app 3000
wiz service start app

# fallback for containers without systemd
sleep 2
if ! pgrep -f "/usr/local/bin/wiz.app" > /dev/null; then
    /usr/local/bin/wiz.app &
fi

tail -f /dev/null
