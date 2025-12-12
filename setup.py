import setuptools
import os

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

import sys

sys.path.append(os.getcwd())
import versioneer

setuptools.setup(
    name="iplotDataAccess",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="Lana Abadie",
    author_email="lana.abadie@iter.org",
    description="Data access for applications using IDSs or CBS",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/iplot-viz/iplotdataaccess.git",
    project_urls={
        "Bug Tracker": "https://jira.iter.org/issues/?jql=project%20%3D%20IDV%20AND%20component%20%3D%20Data-Access",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        # "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "."},
    packages=setuptools.find_namespace_packages(where="."),
    python_requires=">=3.8",
    install_requires=[
        "cachetools >= 4.2.0",
        "iplotLogging >= 0.2.0",
        "requests >= 2.25.1",
        "sseclient-py >= 1.7",
        "PyYAML",
        "pyarrow >= 22.0.0",
        "h5py"
    ],
    package_data={
        "iplotDataAccess": ["data_sources.cfg"],
    },
)
