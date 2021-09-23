import setuptools
from iplotDataAccess._version import __version__

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="iplotDataAccess",
    setup_requires=[
        "setuptools-git-versioning"
    ],
    version_config={
        "version_callback": __version__,
        "template": "{tag}",
        "dirty_template": "{tag}.dev{ccount}.{sha}",
    },
    author="Lana Abadie",
    author_email="lana.abadie@iter.org",
    description="Data access for applications using IDSs or CBS",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://git.iter.org/scm/vis/data-access.git",
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
        "iplotProcessing >= 0.1.0"
    ]
)
