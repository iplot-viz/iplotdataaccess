import iplotLogging.setupLogger as setupLog
import os
import re

import pandas as pd
from iplotDataAccess import dataCommon

logger = setupLog.get_logger(__name__)


class CsvAccess:
    def __init__(self, folder_path):
        self.folder_path = folder_path

    def connect_source(self):
        pass

    def get_data(self, **kwargs):

        data_obj = dataCommon.DataObj()
        path = self.transform_pulse_to_file(kwargs.get("pulse"))
        data = pd.read_csv(path)
        sub_data = data.filter(like=kwargs.get("varname"))
        if len(sub_data.columns) != 1:
            data_obj.set_err(-1, "Multiple columns with same variable name")
            return data_obj
        data_obj.set_data(sub_data.iloc[:, 0].values, 2)

        yunit = re.findall(r' \((.*?)\)', sub_data.columns[0])
        if yunit:
            data_obj.yunit = yunit[0]
        data_obj.set_data(data["Time"].values, 1)
        data_obj.xunit = "s"
        return data_obj

    def clear_cache(self):
        pass

    def get_envelope(self):
        pass

    def get_pulses(self, pattern='.*'):
        all_pulses = {}
        base_folder = os.path.basename(self.folder_path)  # Get the last part of the base folder path

        for folder, _, files in os.walk(self.folder_path):
            # Get the relative path of the current folder compared to self.folder_path
            relative_folder = os.path.relpath(folder, self.folder_path)

            # Combine the base folder with the relative folder path
            combined_folder = f"{base_folder}/{relative_folder}" if relative_folder != '.' else base_folder

            for file in files:
                # Create the key using the combined folder and cleaned file name
                value = f"{combined_folder}:{file.replace('.csv', '').replace('data_', '')}"
                if re.match(pattern, value):
                    all_pulses[value] = {}

        return all_pulses

    def get_pulse_info(self):
        pass

    def get_cbs_list(self, pattern='.*'):
        all_variables = set()
        for folder, _, files in os.walk(self.folder_path):
            for file in files:
                file_path = os.path.join(folder, file)  # Get the full path of the file
                try:
                    with open(file_path, 'r') as f:
                        x = f.readline().split(",")[1:]
                        all_variables = all_variables.union([i.split(" ")[0] for i in x])

                except Exception as e:
                    print(f"Could not open file {file_path}: {e}")
        filtered_vars = [variable for variable in all_variables if re.match(pattern, variable)]
        return filtered_vars

    def get_var_list(self, pattern=".*"):
        return self.get_cbs_list(pattern)

    def get_var_fields(self):
        pass

    def transform_pulse_to_file(self, pulse):
        folders, file = pulse.split(":", 1)
        folders = folders.replace("/", os.sep)
        result = f"{os.path.dirname(self.folder_path)}{os.sep}{folders}{os.sep}data_{file}.csv"
        return result
