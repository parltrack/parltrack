#!/bin/sh

today=$(date -Idate)
cp /tmp/${today}.log /var/www/parltrack/logs/${today}.log
lzip -9 /var/www/parltrack/logs/${today}.log
