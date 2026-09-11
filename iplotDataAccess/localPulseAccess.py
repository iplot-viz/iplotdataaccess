"""Local filesystem IMAS pulse scanner """


import os
from typing import Dict

import pandas as pd
from iplotLogging import setupLogger

from iplotDataAccess.simdbAccess import EMPTY_DF, SIMDB_COLUMNS

logger = setupLogger.get_logger(__name__)

def _has_hdf5(files):
    """True if directory looks like an IMAS HDF5 files
    """
    for f in files:
        if f == "master.h5":
            return True
    return False


def _has_nc(files):
    return any(f.endswith(".nc") for f in files)


def _has_tree(files):
    return any(f.endswith(".tree") for f in files)


_BACKEND_MAP = [
    (_has_hdf5,  "imas:hdf5?path={dir}"),
    (_has_nc,    "imas:hdf5?path={dir}"),
    (_has_tree,  "imas:mdsplus?path={dir}"),
]


class LocalPulseScanner:
    """Scan a local folder tree for IMAS pulse data files."""

    def __init__(self, folder: str):
        if not os.path.isabs(folder):
            raise ValueError(
                f"pulse_list_folder must be an absolute path, got: {folder!r}"
            )
        self.folder = folder

    def fetch_pulses(self) -> pd.DataFrame:
        if not os.path.isdir(self.folder):
            logger.warning(f"Local pulse folder does not exist: {self.folder}")
            return EMPTY_DF.copy()

        found: Dict[str, str] = {}

        for root, _dirs, files in os.walk(self.folder):
            dir_path = os.path.abspath(root)
            if dir_path in found:
                continue  # already added this directory

            for detector, uri_template in _BACKEND_MAP:
                if detector(files):
                    found[dir_path] = uri_template.format(dir=dir_path)
                    break

        if not found:
            logger.info(f"No supported IMAS files found under: {self.folder}")
            return EMPTY_DF.copy()

        rows = []
        for dir_path, imas_uri in sorted(found.items()):
            row = {col: "" for col in SIMDB_COLUMNS}
            row["alias"] = dir_path
            row["imas_uri"] = imas_uri
            row["source"] = "local"
            rows.append(row)

        df = pd.DataFrame(rows, columns=SIMDB_COLUMNS)
        return df
