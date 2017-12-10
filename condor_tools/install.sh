#!/bin/bash

SRCDIR=$(cd $(dirname $0); pwd)

cp $SRCDIR/bin/reqgen.py /usr/local/bin/
cp $SRCDIR/bin/condor_submit /usr/local/bin/
cp $SRCDIR/libexec/collect_history /usr/local/libexec/

cp $SRCDIR/data/cms_sites.list /var/spool/condor/

LIBDIR=/usr/lib/python2.6/site-packages/condor_tools
if ! [ -d $LIBDIR ]
then
  mkdir -p $LIBDIR
  touch $LIBDIR/__init__.py
fi

cp $SRCDIR/lib/history_db.py $LIBDIR/
cp $SRCDIR/lib/collect_history.py $LIBDIR/
cp $SRCDIR/lib/condor_submit.py $LIBDIR/

[ -e /usr/bin/condor_submit ] && mv /usr/bin/{,.}condor_submit

WEBDIR=/var/www/html/condor_history/
[ -d $WEBDIR ] || mkdir -p $WEBDIR
cp -r $SRCDIR/web/html/condor_history/* $WEBDIR