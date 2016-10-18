#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

cp $SRCDIR/reqgen.py /usr/local/bin/
cp $SRCDIR/cms_sites.list /var/spool/condor/
