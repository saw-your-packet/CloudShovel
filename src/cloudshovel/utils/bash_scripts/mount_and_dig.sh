#!/bin/bash

if [ $# -lt 1 ]; then
        echo "[*] Usage: $0 <devices>"
        echo "    Multiple devices should be separated by spaces."
        echo "    E.g.: $0 /dev/sdf /dev/sdg"
        exit
fi

if [ "$EUID" -ne 0 ]; then
    echo "[*] This script must be run as root. Exiting."
    exit 1
fi

mount_and_search(){
    if [ $# -lt 1 ]; then
        echo " [!] Function $0 requires 1 argument. Something went wrong since no arguments were passed."
        return 1
    fi

    dev=$1
    echo "[x] Trying to mount $dev"
    if udisksctl mount -b $dev ; then
        mount_folder=$(udisksctl info -b $dev | grep MountPoints | tr -s ' ' | cut -d ' ' -f 3)
        echo "[x] Mount successful for $dev at $mount_folder"

        mkdir /home/ec2-user/OUTPUT/$counter 2>/dev/null
        cd $mount_folder
        mount_point=.
        
        find $mount_point \( ! -path "$mount_point/proc/*" -a ! -path "$mount_point/Windows/*" -a ! -path "$mount_point/usr/*" -a ! -path "$mount_point/sys/*" -a \
                         ! -path "$mount_point/mnt/*" -a ! -path "$mount_point/dev/*" -a ! -path "$mount_point/tmp/*" -a ! -path "$mount_point/sbin/*" -a \
                         ! -path "$mount_point/bin/*" -a ! -path "$mount_point/lib*" -a ! -path "$mount_point/boot/*" -a ! -path "$mount_point/Program Files/*" -a \
                         ! -path "$mount_points/Program Files \(x86\)/*" \) \
                         -not -empty > /home/ec2-user/OUTPUT/$counter/all_files_cloud_quarry.txt

        for item in $(find $mount_point \( ! -path "$mount_point/Windows/*" -a ! -path "$mount_point/Program Files/*" -a ! -path "$mount_point/Program Files \(x86\)/*" \) -size -25M \
                    \( -name ".aws" -o -name ".ssh" -o -name "credentials.xml" \
                    -o -name "secrets.yml" -o -name "config.php" -o -name "_history" \
                    -o -name "autologin.conf" -o -name "web.config" -o -name ".env" \
                    -o -name ".git" \) -not -empty)
        do
            echo "[+] Found $item. Copying to output..."
            save_name_item=${item:1}
            save_name_item=${save_name_item////\\}
            cp -r $item /home/ec2-user/OUTPUT/$counter/${save_name_item}
        done

        if [ -d "$mount_point/var/www" ]; then
        echo "Web Server Present in /var/www" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
        fi
        if [ -d "$mount_point/inetpub" ]; then
            echo "Web Server Present in /inetpub" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
        fi
        if [ -d "$mount_point/usr/share/nginx/" ]; then
            echo "Web Server Present in /usr/share/nginx" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
        fi

        echo "[x] Unmounting $dev"
        udisksctl unmount -b $dev -f

        return 0
    else return 1
    fi
}

counter=1
something_was_searched=0
mkdir /home/ec2-user/OUTPUT 2>/dev/null

echo "[*] Mounting $# devices ($@):"
for dev in "$@"; do
    device_was_searched=0
    echo "[x] Devices: "
    blkid -o device -u filesystem ${dev}*
    for device in $(blkid -o device -u filesystem ${dev}*); do if mount_and_search $device; then ((counter++)) && something_was_searched=1 && device_was_searched=1; fi done

    if [ $device_was_searched -eq 0 ]; then
        echo " [!] Mounting and secret searching for $dev did not work" 
    fi
done

if [ $something_was_searched -eq 0 ]; then
    echo " [!] Mounting or scanning not successful. Check output for lsblk:"
    lsblk --output NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID,LABEL
    exit 3
fi
