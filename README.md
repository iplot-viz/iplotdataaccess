# Data Access Library

Data access for applications represented using Interface Data Structures (IDSs) or Control Breakdown Structure (CBS).

## Requirements

1. **python <= 3.11**
2. **Dependencies**: Managed
   via [pyproject.toml](https://github.com/iplot-viz/iplotdataaccess/blob/develop/pyproject.toml).

## Installation

Install the package from PyPi:

  ```bash
  pip install iplotDataAccess
  ```

### Installation with optional dependencies

You can also install optional dependencies (e.g. imaspy and test):

  ```bash
  pip install "iplotDataAccess[imaspy, test]"
  ```

#### List of optional dependencies

- ```imaspy```:  installs required packages.
- ```test```: installs required packages to run the tests with pytest.

### Usage Example

  ```bash
  from iplotDataAccess.dataAccess import DataAccess

   # Create a DataAccess object
   da = DataAccess()
   
   # Example: load data from CODAC UDA source
   data_obj = da.get_data("codacuda", varname="IC_ICH1_FAFB_MEAS/phase", tsS="2018-11-21T09:30:00", tsE="2018-11-21T09:45:00", nbp=-1)
   print(data_obj.xdata, data_obj.ydata)
  ```

### Contributing

1. Fork it!
2. Create your feature branch: ```git checkout -b my-new-feature ```
3. Commit your changes: ```git commit -am 'Add some feature' ```
4. Push to the branch:```git push origin my-new-feature ```
5. Submit a pull request