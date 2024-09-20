#!/bin/bash

if test -f /usr/local/bin/ntfs-3g.probe; then
    echo "[x] Library ntfs-3g already installed"
    exit
fi

cd /home/ec2-user/
wget -O ntfs.tgz https://www.tuxera.com/opensource/ntfs-3g_ntfsprogs-2017.3.23.tgz
tar -xf ntfs.tgz
yum groupinstall "Development Tools" -y
cd ntfs-3g_ntfsprogs-2017.3.23/ && ./configure --prefix=/usr/local --disable-static
make
make install
echo "[x] Installation done"
