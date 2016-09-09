#!/bin/bash

function usage() {
  echo "addWork.sh [OPTIONS] USER"
  echo ""
  echo "OPTIONS:"
  echo "    -a  Add work directories for USER"
  echo "    -d  Delete work directories for USER"
  echo "    -s  Target file system (default: /local/d01)"
  echo "    -q  Quota template (default: root)"
  echo ""
  exit 0
}

ACTION=
TARGETFS=/local/d01
QUOTATEMP=root

while [ $# -gt 1 ]
do
  case $1 in
    -a)
        ACTION=add
        shift
        ;;
    -d)
        ACTION=delete
	shift
	;;
    -s)
	TARGETFS=$2
	shift 2
	;;
    -q)
	QUOTATEMP=$2
	shift 2
	;;
    *)
	usage
	;;
  esac
done

if ! [ $ACTION ]
then
  usage
fi

USER=$1

[ $USER ] || usage

if ! id $USER > /dev/null 2>&1
then
  echo "User $USER does not appear to be valid."
  exit 1
fi

if [ $ACTION = "add" ]
then
  
  if ! [ -d $TARGETFS ]
  then
    echo "No such file system: $TARGETFS"
    exit 1
  fi
  
  mkdir $TARGETFS/$USER
  chown $USER:$USER $TARGETFS/$USER
  
  ln -s $TARGETFS/$USER /work/$USER
  
  edquota -f $TARGETFS -p $QUOTATEMP $USER

elif [ $ACTION = "del" ]
then

  TARGET=$(readlink /work/$USER)
  
  echo "Delete $TARGET? (Y/n):"
  read RESP
  [ $RESP = "Y" ] || exit 0

  rm /work/$USER
  rm -rf $TARGET
  
  TARGETFS=$(dirname $TARGET)

  setquota -u $USER 0 0 0 0 $TARGETFS

fi
