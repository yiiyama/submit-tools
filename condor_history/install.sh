#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

cp $SRCDIR/{update.py,db.py} /usr/local/libexec/condor_history

cp -r $SRCDIR/web/html/* /var/www/html/condor_history/
