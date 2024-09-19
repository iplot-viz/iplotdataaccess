#!/bin/bash
# Bamboo script
# Stage 2 : Unit tests

# Set up environment
. ci-build/st00-header.sh $* || exit 1

# Unzip artifact
try tar -xvzf ${PREFIX_DIR}.tar.gz ./${PREFIX_DIR}

# run tests
ABSP=$(get_abs_filename "./${PREFIX_DIR}")
export PYTHONPATH=${PYTHONPATH}:${ABSP}/lib/python3.11/site-packages
try python3 -m pytest --junit-xml=${PREFIX_DIR}/test_report.xml iplotDataAccess
