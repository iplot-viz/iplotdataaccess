"""
Unit tests for reading a pulse identified directly by a netCDF file path.

This covers the feature added in imaspyAccess.IMASPYDataAccess where a pulse ID
that is neither in the "pulse/run" form nor a full "imas:" URI is treated as a
path (e.g. to a self-described netCDF file) and passed straight to imas.DBEntry.

The sample data used here is a small, public IMAS-Data-Dictionary netCDF file
published on Zenodo (https://zenodo.org/records/17062700), so these tests can
run in any environment with network access and the `imas-python[netcdf]`
package installed -- no ITER-internal IMAS Access Layer / shared filesystem is
required.
"""

import importlib.util
import json
import os
import tempfile

import numpy as np
import pytest

# These tests need imas-python; skip cleanly if it is not installed.
if importlib.util.find_spec("imaspy") is None and importlib.util.find_spec("imas") is None:
    pytest.skip("imas/imaspy package required", allow_module_level=True)

from iplotDataAccess.dataAccess import DataAccess
from iplotDataAccess.imaspyAccess import IMASPYDataAccess

DSCFG = json.dumps(
    {
        "imaspy": {
            "type": "IMASPY",
            "database": "ITER",
            "path": "public",
            "backend": "HDF5",
        }
    }
)


class TestIsPulseRun:
    """Direct unit tests for IMASPYDataAccess.is_pulse_run."""

    @pytest.fixture
    def access(self):
        return IMASPYDataAccess(name="imaspy_test", config={})

    @pytest.mark.parametrize("value", ["53298/1", "130012/5", "1/1", "0/0", "53298\\1"])
    def test_pulse_run_forms_are_detected(self, access, value):
        assert access.is_pulse_run(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "imas:hdf5?path=/work/imas/shared/imasdb/ITER/3/105027/2",
            "/tmp/iter_scenario_53298_seq1_DD4.nc",
            "iter_scenario_53298_seq1_DD4.nc",
            "53298",
            "53298/1/2",
            "abc/1",
            "",
        ],
    )
    def test_non_pulse_run_forms_are_rejected(self, access, value):
        assert access.is_pulse_run(value) is False


class TestIMASAccessByNetCDFPath:
    """Test IMAS data access when the pulse is a plain netCDF file path."""

    def setup_method(self) -> None:
        self.temp_config_fd, self.temp_config_path = tempfile.mkstemp(
            suffix=".cfg", prefix="test_imas_netcdf_"
        )
        with open(self.temp_config_path, mode="w") as fp:
            fp.write(DSCFG)
        os.environ["IPLOT_SOURCES_CONFIG"] = os.path.abspath(self.temp_config_path)

        self.da = DataAccess()
        self.ds = "imaspy"
        assert self.da.load_config(), "Failed to load data source configuration"

    def teardown_method(self) -> None:
        try:
            os.close(self.temp_config_fd)
            os.remove(self.temp_config_path)
        except (OSError, FileNotFoundError):
            pass
        os.environ.pop("IPLOT_SOURCES_CONFIG", None)

    def test_core_profiles_1d_profile(self, zenodo_netcdf_pulse) -> None:
        """A 1D radial profile (electron temperature vs rho_tor_norm)."""
        dobj = self.da.get_data(
            self.ds,
            varname="core_profiles/profiles_1d[0]/electrons/temperature",
            pulse=zenodo_netcdf_pulse,
            nbp=-1,
        )

        assert dobj.errcode == 0, dobj.errdesc
        assert np.shape(dobj.xdata) == (298,)
        assert np.shape(dobj.ydata) == (298,)
        assert dobj.yunit == "eV"
        assert dobj.ydata[0] == pytest.approx(20304.058, abs=1e-2)
        assert dobj.ydata[-1] == pytest.approx(495.446, abs=1e-2)

    def test_equilibrium_1d_profile(self, zenodo_netcdf_pulse) -> None:
        """A second 1D profile from a different IDS (safety factor vs psi)."""
        dobj = self.da.get_data(
            self.ds,
            varname="equilibrium/time_slice[0]/profiles_1d/q",
            pulse=zenodo_netcdf_pulse,
            nbp=-1,
        )

        assert dobj.errcode == 0, dobj.errdesc
        assert np.shape(dobj.xdata) == (298,)
        assert np.shape(dobj.ydata) == (298,)
        assert dobj.xunit == "Wb"

    def test_equilibrium_2d_contour_data(self, zenodo_netcdf_pulse) -> None:
        """2D contour data (poloidal flux psi on the equilibrium grid)."""
        dobj = self.da.get_data(
            self.ds,
            varname="equilibrium/time_slice[0]/profiles_2d[0]/psi",
            pulse=zenodo_netcdf_pulse,
            nbp=-1,
        )

        assert dobj.errcode == 0, dobj.errdesc
        assert np.shape(dobj.xdata) == (299,)
        assert np.shape(dobj.ydata) == (299, 299)
        assert dobj.yunit == "Wb"

    def test_summary_scalar_time_series(self, zenodo_netcdf_pulse) -> None:
        """Scalar time series data (this file has a single time slice)."""
        dobj = self.da.get_data(
            self.ds,
            varname="summary/fusion/power/value",
            pulse=zenodo_netcdf_pulse,
            nbp=-1,
        )

        assert dobj.errcode == 0, dobj.errdesc
        assert np.shape(dobj.xdata) == (1,)
        assert np.shape(dobj.ydata) == (1,)
        assert dobj.xunit == "s"
        assert dobj.yunit == "W"
        assert dobj.xdata[0] == pytest.approx(465.0495, abs=1e-3)
        assert dobj.ydata[0] == pytest.approx(1.11733185e08, rel=1e-6)
