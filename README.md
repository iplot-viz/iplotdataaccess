# Data Access Library
Data access for applications represented using IDSs or CBS

## Installation
For backward-compatible installation:
```bash
pip install .
```

## Installation with optional dependencies
Some data sources require additional dependencies. For example, if using IMASPY sources, install the library with PyYaml
as follows:

```bash
pip install .[imaspy]
```

## Requirements
1. python >= 3.8
2. Dependencies are maneged within pyproject.toml. For a complete list of dependencies, see [pyproject.toml](https://git.iter.org/projects/VIS/repos/iplotdataaccess/browse/pyproject.toml)
