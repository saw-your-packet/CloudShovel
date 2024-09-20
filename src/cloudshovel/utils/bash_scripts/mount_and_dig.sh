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

# Installing udisksctl
yum install udisks2 -y

check_and_fix_uuid() {
    local dev=$1
    local uuid=$(blkid -s UUID -o value $dev)
    local fs_type=$(blkid -s TYPE -o value $dev)
    
    if [ "$fs_type" == "xfs" ]; then
        # Check if this UUID is already in use
        if grep -q $uuid /etc/fstab || blkid | grep -v $dev | grep -q $uuid; then
            echo "[!] UUID collision detected for $dev"
            echo "[*] Generating new UUID for $dev"
            
            # Generate new UUID
            xfs_admin -U generate $dev
            
            # Get the new UUID
            new_uuid=$(blkid -s UUID -o value $dev)
            echo "[*] New UUID for $dev: $new_uuid"
        fi
    fi
}

mount_and_search(){
    if [ $# -lt 1 ]; then
        echo " [!] Function $0 requires 1 argument. Something went wrong since no arguments were passed."
        return 1
    fi

    dev=$1
    echo "[x] Trying to mount $dev"

    # Check if the filesystem is NTFS
    fs_type=$(blkid -o value -s TYPE $dev)
    if [ "$fs_type" == "ntfs" ]; then
        echo "[x] NTFS filesystem detected. Using ntfs-3g driver."
        mount_point="/mnt/ntfs_$RANDOM"
        mkdir -p $mount_point
        if mount -t ntfs-3g $dev $mount_point; then
            echo "[x] Mount successful for $dev at $mount_point"
        else
            echo "[!] Failed to mount NTFS volume $dev"
            rmdir $mount_point
            return 1
        fi
    elif [ "$fs_type" == "xfs" ]; then
        echo "[x] XFS filesystem detected."
        # Check and fix UUID if necessary
        check_and_fix_uuid $dev

        mount_point="/mnt/xfs_$RANDOM"
        mkdir -p $mount_point
        if mount -t xfs $dev $mount_point; then
            echo "[x] Mount successful for $dev at $mount_point"
        else
            echo "[!] Failed to mount XFS volume $dev"
            rmdir $mount_point
            return 1
        fi
    else
        if udisksctl mount -b $dev ; then
            mount_point=$(udisksctl info -b $dev | grep MountPoints | tr -s ' ' | cut -d ' ' -f 3)
            echo "[x] Mount successful for $dev at $mount_point"
        else
            echo "[!] Failed to mount $dev"
            return 1
        fi
    fi

    mkdir /home/ec2-user/OUTPUT/$counter 2>/dev/null
    cd $mount_point
    
    find . \( ! -path "./proc/*" -a ! -path "./Windows/*" -a ! -path "./usr/*" -a ! -path "./sys/*" -a \
             ! -path "./mnt/*" -a ! -path "./dev/*" -a ! -path "./tmp/*" -a ! -path "./sbin/*" -a \
             ! -path "./bin/*" -a ! -path "./lib*" -a ! -path "./boot/*" -a ! -path "./Program Files/*" -a \
             ! -path "./Program Files (x86)/*" \) \
             -not -empty > /home/ec2-user/OUTPUT/$counter/all_files_cloud_quarry.txt

    for item in $(find . \( ! -path "./Windows/*" -a ! -path "./Program Files/*" -a ! -path "./Program Files (x86)/*" \) -size -25M \
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

    if [ -d "./var/www" ]; then
    echo "Web Server Present in /var/www" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
    fi
    if [ -d "./inetpub" ]; then
        echo "Web Server Present in /inetpub" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
    fi
    if [ -d "./usr/share/nginx/" ]; then
        echo "Web Server Present in /usr/share/nginx" > /home/ec2-user/OUTPUT/$counter/web_server_true.txt
    fi

    echo "[x] Unmounting $dev"
    if [ "$fs_type" == "ntfs" ] || [ "$fs_type" == "xfs" ]; then
        umount $mount_point
        rmdir $mount_point
    else
        udisksctl unmount -b $dev -f
    fi

    return 0
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