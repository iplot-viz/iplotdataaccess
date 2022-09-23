#!/bin/bash

# 3-fingered-claw 
function yell () 
{ 
  echo "$0: $*" >&2
}

function die () 
{ 
  yell "$*"; exit 1
}

function try () 
{ 
  "$@" || die "cannot $*" 
}


# Default to foss toolchain
if [[ "$1" == "foss" || -z $1 ]];
then
    toolchain=foss
elif [[ "$1" == "intel" ]];
then
    toolchain=intel
fi
echo "Toolchain: $toolchain"

# Clean slate
try module purge

# Other IDV components
try module load iplotLogging/0.2.2-GCCcore-10.2.0

# Testing/Coverage requirements
try module load coverage/5.5-GCCcore-10.2.0

case $toolchain in

  "foss")
      try module load IMAS/3.37.0-4.11.0-foss-2020b
      try module load m-uda-client/7.0-foss-2020b
    ;;
  "intel")
      try module load IMAS
      try module load m-uda-client/7.0-intel-2020b
    ;;
   *)
    echo "Unknown toolchain $toolchain"
    ;;
esac
try module list -t 2>&1
