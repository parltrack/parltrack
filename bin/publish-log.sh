#!/bin/sh

today=${1:-$(date -Idate)}
sync /tmp/${today}.log
cp /tmp/${today}.log /var/www/parltrack/logs/${today}.log
./lf.py html warn < /var/www/parltrack/logs/${today}.log >/var/www/parltrack/logs/${today}.html
sync /var/www/parltrack/logs/${today}.html
lzip -9 /var/www/parltrack/logs/${today}.log
