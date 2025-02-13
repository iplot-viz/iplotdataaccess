import logging
import os
import re
from datetime import datetime
from functools import lru_cache
from glob import iglob
from pathlib import Path

import imaspy as imas
import yaml

logger = logging.getLogger(f"module.{__name__}")


class IMASDBMaster:
    ALL_BACKENDS = "mdsplus", "hdf5"

    @staticmethod
    def get_user_dir(user: str = None):
        """
        The function `get_user_dir` returns the database directory path for a given user or the current user's directory
        path if no user is specified.

        Args:
            user (str): The `user` parameter is a string that represents the username of the user for whom the
                directory path is being retrieved. If the `user` parameter is not provided or is `None`, it will
                default to the current logged-in user obtained using `os.getlogin()`.

        Returns:
            a file path. If the user is not specified or is "public", it returns the file path to the
            "public/imasdb/" directory in the user's home directory. If the user is not "public", itreturns the
            file path to the "shared/imasdb/" directory in the IMAS_HOME directory.
        """
        if not user:
            user = os.getlogin()
        if user != "public":
            return f'{os.path.expanduser(f"~{user}")}/public/imasdb/'
        imas_home_dir = os.environ["IMAS_HOME"]
        if imas_home_dir is None:
            raise FileNotFoundError(
                "File path in the environment variable IMAS_HOME is not defined."
            )
        return f"{imas_home_dir}/shared/imasdb/"

    @staticmethod
    def get_database_dir(database: str, user: str = None):
        """
        The function `get_database_dir` returns the directory path for a given database, and raises an error
        if the path does not exist.

        Args:
            database (str): The `database` parameter is a string that represents the name of the database
                file or directory.
            user (str): The `user` parameter is an optional parameter that represents the user for whom the
                database directory is being retrieved.

        Returns:
            the directory path of the specified database if it exists. If the database does not exist, it
            raises a FileNotFoundError. If the database parameter is None, it returns None.
        """
        user_dir = IMASDBMaster.get_user_dir(user)

        if database is not None:
            user_database_dir = user_dir + database
            if os.path.exists(user_database_dir):
                return user_database_dir
            else:
                raise FileNotFoundError(
                    "The path provided does not exist or has no such database file or directory. \
                        Please check spelling."
                )
        return None

    def get_database_files(
        pulse="",
        run="",
        user=None,
        database=None,
        version=None,
        backends=None,
    ):
        result = []

        if not backends:
            backends = IMASDBMaster.ALL_BACKENDS
        else:
            backends = backends.split(",")
        databases = [database] if database else IMASDBMaster.get_databases(user)
        for database in databases:
            database_files = []
            versions = (
                [version] if version else IMASDBMaster.get_versions(database, user)
            )
            for _version in versions:
                pulses = []
                for backend in backends:
                    if backend == "hdf5":
                        dbs = IMASDBMaster.get_hdf5_pulses(
                            pulse,
                            run,
                            user,
                            database,
                            _version,
                            as_dictionary=True,
                        )
                    elif backend == "mdsplus":
                        dbs = IMASDBMaster.get_mds_plus_pulses(
                            pulse,
                            run,
                            user,
                            database,
                            _version,
                            as_dictionary=True,
                        )
                    else:
                        raise NotImplementedError(f"Unsupported backend: {backend}")
                    if dbs:
                        pulses.append((backend, dbs))
                if pulses:
                    database_files.append((_version, pulses))
            if database_files:
                result.append((database, database_files))
        return result

    @staticmethod
    def get_databases(user: str = None) -> list:
        """
        The function `get_databases` returns a sorted list of databases in a user's directory.

        Args:
            user (str): The `user` parameter is a string that represents the username of the user
                for whom the databases are being retrieved.

        Returns:
            a list of databases.
        """
        user_dir = IMASDBMaster.get_user_dir(user)
        databases = [
            _database
            for _database in os.listdir(user_dir)
            if os.path.isdir(os.path.join(user_dir, _database))
        ]
        return sorted(databases)

    @staticmethod
    def get_versions(database: str, user: str = None) -> list:
        """
        The function `get_versions` returns a sorted list of versions in a given database directory.

        Args:
            database (str): A string representing the name of the database.
            user (str): The `user` parameter is an optional parameter

        Returns:
            a sorted list of versions.
        """
        database_dir = IMASDBMaster.get_database_dir(database, user)
        versions = [
            _version
            for _version in os.listdir(database_dir)
            if os.path.isdir(os.path.join(database_dir, _version))
        ]
        return sorted(versions)

    @staticmethod
    def get_version_dir(version: str, database: str, user: str = None):
        """
        The function `get_version_dir` returns the directory path for a specific version of a database,
        given the version, database name, and optional user.

        Args:
            version (str): The version parameter is a string that represents the version of the database.
            database (str): The `database` parameter is a string that represents the name of the database.
            user (str): The `user` parameter is an optional parameter

        Returns:
            the directory path for the specified version of a database. If the version directory exists,
            it returns the path. If the version directory does not exist, it raises a FileNotFoundError.
            If the version parameter is None, it returns None.
        """
        database_dir = IMASDBMaster.get_database_dir(database, user)
        if version is not None:
            version_dir = f"{database_dir}/{version}"
            if os.path.exists(version_dir):
                return version_dir
            else:
                raise FileNotFoundError(
                    "The path provided does not exist or has no such database file or directory.Please check spelling"
                )
        return None

    @staticmethod
    def get_pulse_status(yaml_file_path) -> str:
        """
        The function `get_pulse_status` reads a YAML file from a given path and returns the value of the
        "status" key in the file's metadata.

        Args:
            yaml_file_path: The `path` parameter is a string that represents the file path to a YAML file.

        Returns:
            the value of the "status" key from the metadata dictionary.
        """
        _yaml_file_path = Path(yaml_file_path)

        status = ""
        with open(_yaml_file_path, "r") as file_handle:
            lines = file_handle.readlines()
            for i, line in enumerate(lines):
                if line.strip().startswith("status:"):
                    start_index = max(0, i - 1)
                    end_index = min(len(lines), i + 2)
                    context = lines[start_index:end_index]
                    combined_context = "".join(context)
                    metadata = yaml.load(combined_context, Loader=yaml.Loader)
                    if isinstance(metadata, dict):
                        status = metadata["status"]
        return status

    @staticmethod
    @lru_cache(maxsize=10)
    def get_hdf5_pulses(
        pulse="",
        run="",
        user: str = None,
        database: str = None,
        version: str = None,
        status="active",
        as_dictionary=False,
    ) -> list:
        """
        The function `get_hdf5_pulses` retrieves a list of pulses from HDF5 master files. It needs to specify
        full path till version.

        Args:
            user (str): The `user` parameter is a string that represents the user for whom the MDSPlus
                pulses are being retrieved.
            database (str): The `database` parameter is a string that represents the name of the database.
                It is used to specify the directory where the MDSplus pulses are stored.
            version (str): The `version` parameter is used to specify the version of the MDSplus database.
                It is a string that represents the version number.
            as_dictionary (bool): The `as_dictionary` parameter is a boolean flag that determines the format
                of the returned pulses. If `as_dictionary` is set to `True`, the pulses will be returned as a
                dictionary where the keys are the pulse numbers and the values are lists of runs associated
                with each pulse.Defaults to False

        Returns:
            a list of tuples. Each tuple contains the following elements, The tuple includes the pulse number,
            run number, HDF5_BACKEND backend, database, user, version, and data file path.
        """
        version_dir = IMASDBMaster.get_version_dir(version, database, user)
        scenario_yaml_dir = os.path.join(version_dir, "0")
        pulses = {} if as_dictionary else []
        hdf5_master_file_paths = iglob(f"{version_dir}/**/*master.h5", recursive=True)

        for hdf5_master_file_path in hdf5_master_file_paths:
            path_parts = hdf5_master_file_path.split("/")
            if len(path_parts) < 3:
                continue

            _run, _pulse = path_parts[-2], path_parts[-3]
            if not _pulse.isdigit() or not _run.isdigit():
                print(
                    f"warning:pulse/run number is not an integer {_pulse}/{_run} {hdf5_master_file_path}"
                )
                continue

            if (run != "" and not _run.startswith(run)) or (
                pulse != "" and not _pulse.startswith(pulse)
            ):
                continue

            _run, _pulse = int(_run), int(_pulse)

            file_time = datetime.fromtimestamp(
                os.path.getmtime(hdf5_master_file_path)
            ).replace(microsecond=0)
            if status:
                yaml_file_path = os.path.join(
                    scenario_yaml_dir, f"ids_{_pulse}{str(_run).zfill(4)}.yaml"
                )
                status_from_yaml = ""
                if os.path.exists(yaml_file_path):
                    status_from_yaml = IMASDBMaster.get_pulse_status(yaml_file_path)
                    if status_from_yaml == "":
                        print(
                            f"warning:could not find status info in scenario file {_pulse}/{_run} {yaml_file_path}"
                        )
                else:
                    print(
                        f"warning:scenario summary file does not exists for {_pulse}/{_run} {yaml_file_path}"
                    )
                    continue
                if status != status_from_yaml:
                    continue
            entry = (
                _pulse,
                _run,
                imas.ids_defs.HDF5_BACKEND,
                database,
                user,
                version,
                hdf5_master_file_path,
                file_time,
            )

            if as_dictionary:
                pulses.setdefault(_pulse, []).append(entry)
            else:
                pulses.append(entry)
        return pulses

    @staticmethod
    @lru_cache(maxsize=10)
    def get_mds_plus_pulses(
        pulse="",
        run="",
        user: str = None,
        database: str = None,
        version: str = None,
        status: str = "active",
        as_dictionary=False,
    ) -> list:
        """
        The function `get_mds_plus_pulses` retrieves a list of MDSPlus pulses based on the provided user, database,
        version, and status parameters.

        Args:
            user (str): The `user` parameter is a string that represents the user for whom the MDSPlus
                pulses are being retrieved.
            database (str): The `database` parameter is a string that represents the name of the database.
                It is used to specify the directory where the MDSplus pulses are stored.
            version (str): The `version` parameter is used to specify the version of the MDSplus database.
                It is a string that represents the version number.
            status (str): The "status" parameter is used to filter the pulses based on their status. If a
                status is provided, only pulses with that status will be included in the result. If no status
                is provided, all pulses will be included.
            as_dictionary (bool): The `as_dictionary` parameter is a boolean flag that determines the format
                of the returned pulses. If `as_dictionary` is set to `True`, the pulses will be returned as a
                dictionary where the keys are the pulse numbers and the values are lists of runs associated
                with each pulse.Defaults to False

        Returns:
            a list of pulses.
        """
        mdsplus_dir = IMASDBMaster.get_version_dir(version, database, user)
        scenario_yaml_dir = os.path.join(mdsplus_dir, "0")
        pulses = {} if as_dictionary else []

        datafile_paths = iglob(f"{mdsplus_dir}/**/*.datafile", recursive=True)

        for data_file_path in datafile_paths:
            root = os.path.dirname(data_file_path)
            datafile = os.path.basename(data_file_path)
            run_list = (root[len(mdsplus_dir) + 1 :]).split("/")
            if len(run_list) == 1:  # AL4 layout
                num_start_pos = datafile.find("_") + 1
                num_end_pos = datafile.rfind(".")
                num = int(datafile[num_start_pos:num_end_pos])
                _pulse = str(num // 10000)
                _run = str(int(run_list[0]) * 10000 + (num % 10000))

            else:  # AL5 layout
                if datafile != "ids_001.datafile":
                    print(
                        f"warning:ids_001.datafile does not exists { _run} {data_file_path}"
                    )
                    continue
                if os.path.islink(data_file_path):
                    continue
                _run = root.split("/")[-1]
                _pulse = root.split("/")[-2]
            if not _pulse.isdigit() or not _run.isdigit():
                print(
                    f"warning:pulse/run number is not an integer {_pulse}/{ _run} {data_file_path}"
                )
                continue
            if (pulse != "" and not _pulse.startswith(pulse)) or (
                run != "" and not _run.startswith(run)
            ):
                continue
            _pulse, _run = int(_pulse), int(_run)

            if status is not None:
                yaml_file = f"ids_{_pulse}{str( _run).zfill(4)}.yaml"
                yaml_file_path = os.path.join(scenario_yaml_dir, yaml_file)
                status_from_yaml = ""
                if os.path.exists(yaml_file_path):
                    status_from_yaml = IMASDBMaster.get_pulse_status(yaml_file_path)
                    if status_from_yaml == "":
                        print(
                            f"warning:could not find status info in scenario file {_pulse}/{ _run} {yaml_file_path}"
                        )
                else:
                    print(
                        f"warning:scenario summary file does not exists for {_pulse}/{ _run} {yaml_file_path}"
                    )
                if status != status_from_yaml:
                    continue

            file_time = datetime.fromtimestamp(
                os.path.getmtime(data_file_path)
            ).replace(microsecond=0)
            entry = (
                _pulse,
                _run,
                imas.ids_defs.MDSPLUS_BACKEND,
                database,
                user,
                version,
                data_file_path,
                file_time,
            )
            if as_dictionary:
                if _pulse not in pulses:
                    pulses[_pulse] = []
                if not any(item[1] == _run for item in pulses[_pulse]):
                    pulses[_pulse].append(entry)
            else:
                pulses.append(entry)
        return pulses
