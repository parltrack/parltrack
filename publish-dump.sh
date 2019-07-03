#!/bin/sh

lzip -c -9 db/$1 >/var/www/parltrack/dumps/$1.lz-new
mv /var/www/parltrack/dumps/$1.lz /var/www/parltrack/dumps/arch/${1%%.json}-$(date -r /var/www/parltrack/dumps/$1.lz -Idate).json
mv /var/www/parltrack/dumps/$1.lz-new /var/www/parltrack/dumps/$1.lz
