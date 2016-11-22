#!/bin/bash

#----------------------------------------------------------------------------------
# submit.sh
#
# Tutorial submit script
#
# This script will call condor_submit to submit NJOBS jobs of executable
# first_test.sh. Place this directory in a directory under /work/$USER.
# Then a simple ./submit.sh will create a job that returns an output in
# /work/$USER/output.
#----------------------------------------------------------------------------------

# Directory where this script is
THISDIR=$(cd $(dirname $0); pwd)

# Path to the executable script
EXECUTABLE=$THISDIR/first_test.sh

# Input files (comma-separated) to be transferred to the remote host
# Executable will see them copied in PWD
INPUT_FILES=$THISDIR/first_test_inputs.tar.gz

# $(Process) is replaced by the job serial id (0 - (NJOBS-1))
ARGUMENTS='$(Process)'

# Destination of output files (if using condor file transfer)
OUTDIR=/work/$USER/output

# Output files (comma-separated) to be transferred back from completed
# jobs to $OUTDIR.  Condor will find these files in the initial PWD of
# the executable Since /work has a limited user quota, users are
# encouraged to not use the condor transfer mechanism but rather
# transfer the job outputs directly to some storage at the end of the jobs.
# If this is done, set this to "".
OUTPUT_FILES='first_test_output_$(Process).txt'

# Destination of log, stdout, stderr files
LOGDIR=/work/$USER/logs

NJOBS=1

# Uncommented -> submit to local test queue
read -d '' LOCALTEST << EOF
+Submit_LocalTest = 5
requirements = isUndefined(GLIDEIN_Site)
EOF

# Make directories if necessary
if ! [ -d $LOGDIR ]
then
  mkdir -p $LOGDIR
fi

if ! [ -d $OUTDIR ]
then
  mkdir -p $OUTDIR
fi

# Now submit the job

echo '
universe = vanilla
executable = '$EXECUTABLE'
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_input_files = '$INPUT_FILES'
transfer_output_files = '$OUTPUT_FILES'
output = '$LOGDIR'/$(Process).stdout
error = '$LOGDIR'/$(Process).stderr
log = '$LOGDIR'/$(Process).log
initialdir = '$OUTDIR'
requirements = Arch == "X86_64"
rank = Mips
arguments = "'$ARGUMENTS'"
'"$LOCALTEST"'
queue '$NJOBS | condor_submit
