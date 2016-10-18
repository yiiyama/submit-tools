#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

cp $SRCDIR/vomsinfo /usr/local/bin/

crontab -l | grep vomsinfo > /dev/null
if [ $? -ne 0 ]
then
  (crontab -l; echo $SRCDIR/crontab) | crontab -
fi
