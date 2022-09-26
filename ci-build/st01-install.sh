#!/bin/bash
# Bamboo script
# Stage 1 : Pip install

# Set up environment
source ci-build/st00-header.sh $* || exit 1

# Create a virtualized environment for installing iplotlib
if [ -d "${PREFIX_DIR}" ];
then
    try rm -r ${PREFIX_DIR}
fi

python -m venv --system-site-packages ${PREFIX_DIR}
source ${PREFIX_DIR}/bin/activate

# Install prerequisities
try python3 -m pip --disable-pip-version-check install --no-deps cachetools
try python3 -m pip --disable-pip-version-check install --no-deps requests
try python3 -m pip --disable-pip-version-check install --no-deps sseclient-py

# Test install command
try python3 -m pip --disable-pip-version-check install --no-deps .

try python3 -c "import iplotDataAccess"

# Stash
tar -cvzf ${PREFIX_DIR}.tar.gz ./${PREFIX_DIR}

# Clean up
try rm -r ${PREFIX_DIR}
