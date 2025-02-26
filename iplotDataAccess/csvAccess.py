import os
import re
import pandas as pd
from pandas import DataFrame

from iplotDataAccess import dataCommon
from iplotDataAccess.dataSource import DataSource


class CsvAccess(DataSource):
    source_type = "CSV"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)

        self.folder_path = config.get("path", "")  # Store the folder path for accessing CSV files

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
        if len(sub_data.columns) != 1:
            data_obj.set_err(-1, "Multiple columns with same variable name")

        # Set the data for the variable in the DataObj
        data_obj.set_data(sub_data.iloc[:, 0].values, 2)

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
        base_folder = os.path.basename(self.folder_path)  # Get the base folder name
        # Walk through all files and folders in the directory
        for folder, _, files in os.walk(self.folder_path):
            relative_folder = os.path.relpath(folder, self.folder_path).replace(os.sep, "/")
            # For each file, create a key with the folder and cleaned file name
            for file in files:
                if not file.endswith(".csv"):
                    continue
                value = f"{relative_folder}:{file.replace('.csv', '').replace('data_', '')}"
                if re.match(pattern, value):
                    all_pulses.append(value)
        # Return the pulses
        return all_pulses

    # Method to get a list of all unique variables from CSV files in the folder
    def get_var_list(self, pattern='.*'):
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
                    print(f"Could not open file {file_path}: {e}")  # Handle file reading errors

        # Filter variables matching the given pattern
        filtered_vars = [variable for variable in all_variables if re.match(pattern, variable)]

        return filtered_vars  # Return the filtered list of variables

    # Method to transform a pulse string into a file path
    # Example: input 'ITER/COMM:111' into
    # '{user_path}\\iplotdataaccess\\iplotDataAccess\\ITER\\COMM\\data_111.csv'
    def transform_pulse_to_file_path(self, pulse):
        # Split the pulse into folder and file
        folders, file = pulse.split(":", 1)
        # Replace slashes with the OS-specific separator
        folders = folders.replace("/", os.sep)
        # Join all parts
        result = f"{self.folder_path}{os.sep}{folders}{os.sep}data_{file}.csv"
        return result  # Return the constructed file path

    def clear_cache(self):
        pass

    def get_envelope(self):
        pass
