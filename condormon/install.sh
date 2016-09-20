#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

mkdir -p /var/run/condormon
mkdir -p /var/www/html/condormon/{imgs,jobs}

cp $SRCDIR/condormon.py /usr/local/bin/condormon.py
cp $SRCDIR/web/html/index.php /var/www/html/condormon/index.php
