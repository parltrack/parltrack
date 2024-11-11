#!/bin/sh

zstd -19 <db/$1 >/var/www/parltrack/dumps/$1.zst-new
sync /var/www/parltrack/dumps/$1.zst-new
[ -f /var/www/parltrack/dumps/$1.zst ] && {
   date=$(date -r /var/www/parltrack/dumps/$1.zst -Idate)
   mv /var/www/parltrack/dumps/$1.zst /var/www/parltrack/dumps/arch/${1%%.json}-${date}.json.zst
}
mv /var/www/parltrack/dumps/$1.zst-new /var/www/parltrack/dumps/$1.zst
