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
try module load iplotLogging

# Testing/Coverage requirements
case $toolchain in

  "foss")
      try module load IMAS-AL-Python/5.3.0-foss-2023b-DD-3.42.0
      try module load m-uda-client/7.2.0-gfbf-2023b
      try module load coverage
    ;;
  "intel")
      try module load IMAS-AL-Python/5.3.0-intel-2023b-DD-3.42.0
      try module load m-uda-client/7.2.0-iimkl-2023b
      try module load coverage
    ;;
   *)
    echo "Unknown toolchain $toolchain"
    ;;
esac
try module -t list 2>&1 | sort

export HOME=$PWD
echo "HOME was set to $HOME"
