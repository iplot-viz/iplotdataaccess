import os
import re
import pandas as pd
from pandas import DataFrame

from iplotDataAccess import dataCommon
from iplotDataAccess.dataSource import DataSource
import iplotLogging.setupLogger as setupLog

logger = setupLog.get_logger(__name__)


class CsvAccess(DataSource):
    source_type = "CSV"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)

        self.folder_path = config.get("path", "")  # Store the folder path for accessing CSV files
        self.def_pulse_location = self.folder_path.split('/')[-1]

    def connect(self) -> bool:
        self.connected = os.path.isdir(self.folder_path)
        return self.connected

    # Method to get data from a CSV file based on the 'pulse' and 'varname' arguments in kwargs
    def get_data(self, **kwargs):

        # Create a DataObj instance for storing the data
        data_obj = dataCommon.DataObj()

        # Transform the 'pulse' argument to a valid file path
        path = self.transform_pulse_to_file_path(kwargs.get("pulse"))

        # Read the CSV file into a pandas DataFrame
        data = pd.read_csv(path)

        if kwargs.get("tsS") is not None:
            data = data[data['Time'] >= kwargs.get("tsS")]
        if kwargs.get("tsE") is not None:
            data = data[data['Time'] <= kwargs.get("tsE")]

        sub_data = data.filter(like=kwargs.get("varname"))

        # If multiple columns match 'varname', return an error
        if len(sub_data.columns) > 1:
            data_obj.set_err(-1, "Multiple columns with same variable name")
            return data_obj

        if len(sub_data.columns) == 0:
            data_obj.set_err(-1, f"No columns found matching variable name '{kwargs.get('varname')}'")
            return data_obj

        # Set the data for the variable in the DataObj
        data_obj.set_data(sub_data.iloc[:, 0].values, 2)
        logger.debug(" found data_obj %s ", data_obj)

        # Extract the unit from the variable's column name (if present)
        yunit = re.findall(r' \((.*?)\)', sub_data.columns[0])
        if yunit:
            data_obj.yunit = yunit[0]

        # Set the 'Time' column data in the DataObj and define xunit as "seconds"
        data_obj.set_data(data["Time"].values, 1)
        data_obj.xunit = "s"

        return data_obj  # Return the populated DataObj

    # Method to get all pulses (files) in the folder matching a pattern as a list
    def get_pulses_df(self, pattern='.*') -> DataFrame:
        all_pulses = []
        pstatus = "completed"

        # Walk through all files and folders in the directory
        for folder, _, files in os.walk(self.folder_path):
            relative_folder = os.path.relpath(folder, self.folder_path).replace(os.sep, "/")
            # For each file, create a key with the folder and cleaned file name
            for file in files:
                if not file.endswith(".csv"):
                    continue
                value = f"{self.def_pulse_location}:{relative_folder}/{file.replace('.csv', '').replace('data_', '')};{pstatus}"
                logger.debug(" found value and file %s %s", value, file)
                if re.match(pattern, value):
                    all_pulses.append(value)

        # Return the pulses
        logger.debug(" pulses  %s", all_pulses)
        return pd.DataFrame([value.split(";") for value in all_pulses], columns=["pulseId", "Status"])

    def get_cbs_list(self, pattern=".*"):
        var_list = self.get_var_list(pattern)
        cbs = set()

        for v in var_list:
            cbs.add(v + "?V")

        logger.debug(" cbs list %s", cbs)
        return cbs

    def get_cbs_dictX(self, pattern='.*') -> dict:
        cbs_list = self.get_cbs_list(pattern)
        cbs_dict = dict()
        for line in cbs_list:
            cur_dict = cbs_dict
            cbs = line.split(":")
            for counter, s in enumerate(cbs):
                data = '-'.join(cbs[0:counter])
                if data not in cur_dict:
                    cur_dict = cur_dict.setdefault(data, {})
            cur_dict = cur_dict.setdefault(line.replace('?V'), '')
        logger.debug(" cbs list %s", cbs_dict)
        return cbs_dict

    def get_cbs_dict(self, pattern='.*') -> dict:
        cbs_list = self.get_cbs_list(pattern)
        cbs_dict = dict()
        for line in cbs_list:
            cur_dict = cbs_dict
            list_line = line.split('-')
            for var in list_line:
                if var.endswith('?V'):
                    cur_dict = cur_dict.setdefault('-'.join(list_line).replace('?V', ''), '')
                else:
                    cur_dict = cur_dict.setdefault(var, {})

        return cbs_dict

    def get_pulse_info(self, pulse, run):
        all_pulses = self.get_pulses_df()
        return None

    def get_var_dict(self, pattern='.*'):
        return self.get_cbs_dict(pattern)

    def is_connected(self):
        return self.connected is not None

    def search_pulses_df(self, text) -> DataFrame:
        return self.get_pulses_df(pattern=text)

    # Method to get a list of all unique variables from CSV files in the folder
    def get_var_list(self, patt='.*'):
        all_variables = set()  # Use a set to store unique variables

        # Walk through all files and folders in the directory
        for folder, _, files in os.walk(self.folder_path):
            for file in files:
                if not file.endswith(".csv"):
                    continue
                file_path = os.path.join(folder, file)  # Get the full file path
                try:
                    # Open each file and read the header line to extract variables
                    with open(file_path, 'r') as f:
                        x = f.readline().split(",")[1:]  # Skip the first column (Time)
                        all_variables = all_variables.union([i.split(" ")[0] for i in x])

                except Exception as e:
                    logger.error("Could not open file %s for %s ", file_path, e)  # Handle file reading errors
        logger.debug(" all variable %s", all_variables)

        # Filter variables matching the given pattern
        filtered_vars = []
        for variable in all_variables:
            s = re.match(patt, variable.strip())

            if s is not None:
                filtered_vars.append(s[0])

        logger.debug(" variable  %s  and pattern %s ", filtered_vars, patt)

        return filtered_vars  # Return the filtered list of variables

    # Method to transform a pulse string into a file path
    # Example: input 'ITER/COMM:111' into
    # '{user_path}\\iplotdataaccess\\iplotDataAccess\\ITER\\COMM\\data_111.csv'
    def transform_pulse_to_file_path(self, pulse):
        # Split the pulse into folder and file
        folders, file = pulse.split(":", 1)
        f1, f2 = file.split("/", 1)
        print(f" variable {pulse} ")
        # Replace slashes with the OS-specific separator
        folders = folders.replace("/", os.sep)
        # Join all parts
        result = f"{self.folder_path}{os.sep}{f1}{os.sep}data_{f2}.csv"
        return result  # Return the constructed file path

    def clear_cache(self):
        pass

    def get_envelope(self):
        pass
