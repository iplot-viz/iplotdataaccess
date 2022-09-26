#!/bin/bash
# Bamboo script
# Stage 3 : Code coverage of unit tests

# Set up environment
. ci-build/st00-header.sh $* || exit 1

# Unzip artifact
tar -xvzf ${PREFIX_DIR}.tar.gz ./${PREFIX_DIR}
ABSP=$(get_abs_filename "./${PREFIX_DIR}")
export PYTHONPATH=${PYTHONPATH}:${ABSP}/lib/python3.8/site-packages

#export PYTHONPATH=${PYTHONPATH}:$(get_abs_filename "./${PREFIX_DIR}")
# run tests
coverage run --source=iplotDataAccess --full-trace -m pytest iplotDataAccess

# report
coverage report -i
