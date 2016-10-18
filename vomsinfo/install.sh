#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

cp $SRCDIR/vomsinfo /usr/local/bin/

crontab -l | grep vomsinfo > /dev/null
if [ $? -ne 0 ]
then
  (crontab -l; cat $SRCDIR/crontab) | crontab -
fi
