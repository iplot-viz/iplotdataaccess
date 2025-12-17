# Data Access Library

Data access for applications represented using Interface Data Structures (IDSs) or Control Breakdown Structure (CBS).

## Requirements

1. **python >= 3.8**
2. **Dependencies**: Managed within 'pyproject.toml' file. For a complete list of required and optional dependencies,
   see the [pyproject.toml](https://github.com/iplot-viz/iplotdataaccess/blob/develop/pyproject.toml) file.

## Installation Methods

### 1. From PyPi

  ```bash
  pip install iplotDataAccess
  ```

### 2. Install from source

Clone the repository and install in editable mode:

  ```bash
  git clone https://github.com/iplot-viz/iplotdataaccess.git
  cd iplotdataaccess
  pip install -e .
  ```

This approach allows you to modify the code locally while using the package.

### Installation with optional dependencies

Some data sources require additional Python packages that are not install by default:

**Important**: Only install the dependencies for the data sources you plan to use. For example:

- If you only use CODAC UDA data sources, you don't need PyYAML.

| Optional Group | Additional Packages Installed |              Installation |
|:---------------|:-----------------------------:|--------------------------:|
| imaspy         |        PyYAML, pyarrow        |   pip install ".[imaspy]" |
| codacuda       |             hdf5              | pip install ".[codacuda]" |

To install all optional dependencies together:

  ```bash
  pip install ".[imaspy,codacuda]"
  ```

### Usage Example

  ```bash
  from iplotDataAccess.dataAccess import DataAccess

   # Create a DataAccess object
   da = DataAccess()
   
   # Example: load data from CODAC UDA source
   data_obj = da.get_data("codacuda", varname="IC_ICH1_FAFB_MEAS/phase", tsS="2018-11-21T09:30:00", tsE="2018-11-21T09:45:00", nbp=-1)
   print(data_obj.xdata, data_obj.ydata)
  ```

