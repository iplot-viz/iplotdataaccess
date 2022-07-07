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
try module load iplotLogging/0.2.1-GCCcore-10.2.0

# Testing/Coverage requirements
try module load coverage/5.5-GCCcore-10.2.0

case $toolchain in

  "foss")
      try module load IMAS/3.36.0-4.10.2-foss-2020b
      try module unload -f Boost
      try module load UDA-CCS/6.3-foss-2020b
    ;;
  "intel")
      try module load IMAS
      try module unload -f Boost
      try module load UDA-CCS/6.3-intel-2020b
      try module load numpy/1.21.0-intel-2020b # Fixes problem with Intel plan
    ;;
   *)
    echo "Unknown toolchain $toolchain"
    ;;
esac

try module list -t 2>&1
