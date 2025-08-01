import logging
import os
import re
import time

import pandas as pd
import yaml

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

from concurrent.futures import ThreadPoolExecutor

from pandas import json_normalize

logger = logging.getLogger("module")

yaml_mapping = {
    "reference_name": "ref_name",
    "responsible_name": "ro_name",
    "characteristics.shot": "pulse",
    "characteristics.run": "run",
    "characteristics.type": "type",
    "characteristics.workflow": "workflow",
    "characteristics.machine": "database",
    "scenario_key_parameters.confinement_regime": "confinement",
    "scenario_key_parameters.plasma_current": "ip",
    "scenario_key_parameters.magnetic_field": "b0",
    "scenario_key_parameters.main_species": "fuelling",
    "scenario_key_parameters.central_electron_density": "ne0",
    "scenario_key_parameters.sepmid_electron_density": "nesep",
    "scenario_key_parameters.central_zeff": "zeff",
    "scenario_key_parameters.sepmid_zeff": "zeff_sep",
    "scenario_key_parameters.density_peaking": "npeak",
    "hcd.p_hcd": "p_hcd",
    "hcd.p_ec": "p_ec",
    "hcd.p_ic": "p_ic",
    "hcd.p_nbi": "p_nbi",
    "hcd.p_lh": "p_lh",
    "hcd.p_sol": "p_sol",
    "free_description": "extra",
    "ids_list": "idslist",
    "tsteps": "tsteps",
    "location": "location",
    "plasma_composition.species": "species",
    "plasma_composition.n_over_e": "pc_n_over_ne",
    "plasma_composition.a": "pc_a",
    "plasma_composition.z": "pc_z",
    "plasma_composition.n_over_ntot": "pc_n_over_ntot",
    "plasma_composition.n_over_n_maj": "pc_n_over_n_maj",
    "lastmodified": "date",
}


# Class is a base class for scenario descriptions.
class IMASDBMaster:
    def __init__(self, directory_list=[]) -> None:
        """
        The function initializes a folder path variable based on the provided input or a default value.

        Args:
            folder_path (str): The `folder_path` parameter is a string that represents the path to a folder.
        """
        self.directory_list = directory_list

    @staticmethod
    def get_yaml_data(yaml_file_path):
        """
        The function `get_yaml_data` reads a YAML file and returns its contents as a Python object.

        Args:
            yaml_file_path: The `yaml_file_path` parameter is a string that represents the file path of the YAML
                file that you want to load and retrieve data from.

        Returns:
            the data loaded from the YAML file.
        """
        if not os.path.exists(yaml_file_path):
            logger.warning(f"YAML file does not exist: {yaml_file_path}")
            return None
        with open(yaml_file_path, "r", encoding="utf-8") as file_handle:
            try:
                yaml_data = yaml.load(file_handle, Loader=Loader)
            except Exception as e:
                logger.debug(f"Error loading YAML file {e}", exc_info=True)
                yaml_data = None
        return yaml_data

    @staticmethod
    def get_data_frame_from_yaml(yaml_file_path, add_obsolete=False):
        """
        The function `get_data_frame_from_yaml` takes a YAML file path, reads the data from the file, checks if
        the status is active (unless `addObsolete` is set to True), converts the data into a flat table, and
        returns it as a pandas DataFrame.

        Args:
            yaml_file_path: The path to the YAML file from which you want to create a DataFrame.
            add_obsolete: The add_obsolete parameter is a boolean flag that determines whether or not to include
                obsolete data in the resulting DataFrame.

        Returns:
            a pandas DataFrame object.
        """
        yaml_data = IMASDBMaster.get_yaml_data(yaml_file_path)
        if yaml_data is None:
            return None
        if add_obsolete is False:
            if yaml_data["status"] != "active":
                return None
        flat_table = json_normalize(yaml_data)
        data_frame = pd.DataFrame(flat_table)
        return data_frame

    def get_dataframes_from_files(self, extension=".yaml", add_obsolete=False):
        """
        The function `get_dataframes_from_files` retrieves data from YAML files, creates dataframes, adds additional
        information, and returns a concatenated dataframe.

        Args:
            extension: The "extension" parameter is a string that specifies the file extension to search for.
            add_obsolete: The "add_obsolete" parameter is a boolean flag that determines whether or not to
                include obsolete data in the resulting dataframes.

        Returns:
            a pandas DataFrame object.
        """
        files = []
        for folder_path in self.directory_list:
            for root, _, filenames in os.walk(folder_path):
                for filename in filenames:
                    if filename.endswith(extension):
                        files.append(os.path.join(root, filename))

        if extension == ".yaml":
            data_frames = []
            append_df = data_frames.append

            def process_yaml_file(yaml_file):
                df = IMASDBMaster.get_data_frame_from_yaml(yaml_file, add_obsolete=add_obsolete)
                if df is not None:
                    df["dd_version"] = ""
                    if "ITER/3/0" in yaml_file or "iterdb/3/0" in yaml_file:
                        df["dd_version"] = "3"
                    elif "ITER/4/" in yaml_file or "iterdb/4/" in yaml_file:
                        df["dd_version"] = "4"

                    df["location"] = yaml_file
                    local_time = time.ctime(os.path.getmtime(yaml_file))
                    df["lastmodified"] = pd.to_datetime(local_time)
                    self._extract_information(df)
                    return df
                return None

            with ThreadPoolExecutor() as executor:
                results = executor.map(process_yaml_file, files)

            for result in results:
                if result is not None:
                    append_df(result)
        df = pd.concat(data_frames, ignore_index=True)
        df = df.rename(columns=yaml_mapping)
        return df

    def _extract_information(self, df):
        """
        The function `_extract_information` extracts information from a DataFrame and adds new columns based
        on the extracted data.

        Args:
            df: The parameter `df` is a pandas DataFrame object.
        """
        if "idslist.summary.time_step_number" in df.columns:
            df["tsteps"] = df["idslist.summary.time_step_number"]

        idslist = set([x.split(".")[1] for x in df.columns if "idslist" in x])
        df["idslist"] = ",".join(idslist)
        species = n_over_ne = None
        if "plasma_composition.species" in df.columns:
            species = str(df["plasma_composition.species"][0])
        if "plasma_composition.n_over_ne" in df.columns:
            n_over_ne = str(df["plasma_composition.n_over_ne"][0])

        if species is not None and n_over_ne is not None:
            species = species.split()
            n_over_ne = n_over_ne.split()

            species_dict = {k: v for k, v in zip(species, n_over_ne)}
            sorted_dict = dict(sorted(species_dict.items(), key=lambda item: float(item[1]), reverse=True))
            df["composition"] = ",".join([f"{key}({value})" for key, value in sorted_dict.items()])
        else:
            df["composition"] = "None"
