#!/bin/sh

lzip -c -9 db/$1 >/var/www/parltrack/dumps/$1.lz-new
sync /var/www/parltrack/dumps/$1.lz-new
[ -f /var/www/parltrack/dumps/$1.lz ] && {
   date=$(date -r /var/www/parltrack/dumps/$1.lz -Idate)
   mv /var/www/parltrack/dumps/$1.lz /var/www/parltrack/dumps/arch/${1%%.json}-${date}.json.lz
}
mv /var/www/parltrack/dumps/$1.lz-new /var/www/parltrack/dumps/$1.lz
