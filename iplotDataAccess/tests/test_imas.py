"""
Test module for IMAS data access functionality.
This module contains regression tests for the DataAccess class
when working with IMASPY data sources.
"""

import unittest
import os
import tempfile
import numpy as np
from iplotDataAccess.dataAccess import DataAccess
try:
    import imas
    imas_imported = True
except ImportError:
    imas_imported = False


dscfg = """{
    "imaspy": {
        "type": "IMASPY",
        "database": "ITER",
        "path": "public",
        "backend": "HDF5"
        }
    }
"""

@unittest.skipUnless(imas_imported, "IMAS not available for CI tests")
class TestIMASAccess(unittest.TestCase):
    """Test class for IMAS data access functionality."""

    @staticmethod
    def _first(arr):
        """Get the first element of an array."""
        if isinstance(arr, np.ndarray) and arr.size > 0:
            return arr.flat[0]
        return "N/A"

    @staticmethod
    def _last(arr):
        """Get the last element of an array."""
        if isinstance(arr, np.ndarray) and arr.size > 0:
            return arr.flat[-1]
        return "N/A"

    def _validate_data_object(
            self,
            dobj,
            expected_x_shape=None,
            expected_y_shape=None,
            expected_x_unit=None,
            expected_y_unit=None,
            expected_x_label=None,
            expected_y_label=None,
            expected_x_values=None,
            expected_y_values=None,
            varname="",
    ):
        """Comprehensive validation of data object properties."""

        # Validate X data shape
        if expected_x_shape is not None:
            actual_x_shape = np.shape(dobj.xdata)
            self.assertEqual(
                actual_x_shape,
                expected_x_shape,
                f"X data shape mismatch for {varname}. Expected: {expected_x_shape}, Got: {actual_x_shape}",
            )

        # Validate Y data shape
        if expected_y_shape is not None:
            actual_y_shape = np.shape(dobj.ydata)
            self.assertEqual(
                actual_y_shape,
                expected_y_shape,
                f"Y data shape mismatch for {varname}. Expected: {expected_y_shape}, Got: {actual_y_shape}",
            )

        # Validate X unit
        if expected_x_unit is not None:
            self.assertEqual(
                dobj.xunit,
                expected_x_unit,
                f"X unit mismatch for {varname}. Expected: '{expected_x_unit}', Got: '{dobj.xunit}'",
            )

        # Validate Y unit
        if expected_y_unit is not None:
            self.assertEqual(
                dobj.yunit,
                expected_y_unit,
                f"Y unit mismatch for {varname}. Expected: '{expected_y_unit}', Got: '{dobj.yunit}'",
            )

        # Validate X label
        if expected_x_label is not None:
            actual_x_label = getattr(dobj, "xlabel", "N/A")
            self.assertEqual(
                actual_x_label,
                expected_x_label,
                f"X label mismatch for {varname}. Expected: '{expected_x_label}', Got: '{actual_x_label}'",
            )

        # Validate Y label
        if expected_y_label is not None:
            actual_y_label = getattr(dobj, "ylabel", "N/A")
            self.assertEqual(
                actual_y_label,
                expected_y_label,
                f"Y label mismatch for {varname}. Expected: '{expected_y_label}', Got: '{actual_y_label}'",
            )

        # Validate X data values
        if (
                expected_x_values is not None
                and isinstance(dobj.xdata, np.ndarray)
                and dobj.xdata.size > 0
        ):
            actual_x_first = self._first(dobj.xdata)
            actual_x_last = self._last(dobj.xdata)
            if len(expected_x_values) >= 2:
                self.assertAlmostEqual(
                    actual_x_first,
                    expected_x_values[0],
                    places=3,
                    msg=f"X data first value mismatch for {varname}",
                )
                self.assertAlmostEqual(
                    actual_x_last,
                    expected_x_values[1],
                    places=3,
                    msg=f"X data last value mismatch for {varname}",
                )

        # Validate Y data values
        if (
                expected_y_values is not None
                and isinstance(dobj.ydata, np.ndarray)
                and dobj.ydata.size > 0
        ):
            actual_y_first = self._first(dobj.ydata)
            actual_y_last = self._last(dobj.ydata)
            if len(expected_y_values) >= 2:
                self.assertAlmostEqual(
                    actual_y_first,
                    expected_y_values[0],
                    places=3,
                    msg=f"Y data first value mismatch for {varname}",
                )
                self.assertAlmostEqual(
                    actual_y_last,
                    expected_y_values[1],
                    places=3,
                    msg=f"Y data last value mismatch for {varname}",
                )

        # Basic data integrity checks
        self.assertIsInstance(
            dobj.xdata,
            (np.ndarray, list),
            f"X data should be numpy array or list for {varname}",
        )
        self.assertIsInstance(
            dobj.ydata,
            (np.ndarray, list),
            f"Y data should be numpy array or list for {varname}",
        )
        self.assertIsInstance(dobj.xunit, str, f"X unit should be string for {varname}")
        self.assertIsInstance(dobj.yunit, str, f"Y unit should be string for {varname}")

        return True

    def setUp(self) -> None:
        """Set up test fixtures before each test method."""
        print(f"\n--- Setting up test: {self._testMethodName} ---")
        super().setUp()

        # Create a temporary file for data source configuration
        self.temp_config_fd, self.temp_config_path = tempfile.mkstemp(
            suffix=".cfg", prefix="test_imas_"
        )

        self.da = DataAccess()
        self.ds = "imaspy"

        # Write configuration to temporary file
        with open(self.temp_config_path, mode="w") as fp:
            fp.write(dscfg)

        # Set environment variable for data sources configuration
        os.environ["DATASOURCESCONF"] = os.path.abspath(self.temp_config_path)
        print(f"Created temporary config file: {self.temp_config_path}")

        # Load configuration and verify it's valid
        if not self.da.load_config():
            self.fail("Failed to load data source configuration")

        print("Data source configuration loaded successfully")

    def tearDown(self) -> None:
        """Clean up test fixtures after each test method."""
        print(f"--- Cleaning up test: {self._testMethodName} ---")

        # Clean up temporary file
        try:
            os.close(self.temp_config_fd)
            os.remove(self.temp_config_path)
            print(f"Removed temporary config file: {self.temp_config_path}")
        except (OSError, FileNotFoundError) as e:
            print(
                f"Warning: Could not remove temporary file {self.temp_config_path}: {e}"
            )

        # Clean up environment variable
        if "DATASOURCESCONF" in os.environ:
            del os.environ["DATASOURCESCONF"]

        super().tearDown()

    def test_IMASAccessByPulse(self) -> None:
        """Test IMAS data access by pulse for various variables with comprehensive validation."""
        print("* Testing IMAS access by pulse for multiple variables...")

        test_cases = [
            {
                "varname": "summary/fusion/power/value",
                "pulse": "130012/5",
                "expected_x_shape": (108,),
                "expected_y_shape": (108,),
                "expected_x_unit": "s",
                "expected_y_unit": "W",
                "expected_x_label": "summary/time",
                "expected_y_label": "fusion/power/value",
                "expected_x_values": [1.5, 398.7086099999997],
                "expected_y_values": [8.184821664754754e-12, 6.965436009020474],
            },
            {
                "varname": "magnetics/flux_loop[1]/flux/data",
                "pulse": "imas:hdf5?path=/work/imas/shared/imasdb/ITER/3/105027/2",
                "expected_x_shape": (614,),
                "expected_y_shape": (614,),
                "expected_x_unit": "s",
                "expected_y_unit": "Wb",
                "expected_x_label": "magnetics/time",
                "expected_y_label": "flux_loop[1]/flux/data",
                "expected_x_values": [0.002, 150.58029973657193],
                "expected_y_values": [58.0792446406959, 0.6802878105754839],
            },
            {
                "varname": "magnetics/flux_loop[0]/flux/data",
                "pulse": "imas:hdf5?path=/work/imas/shared/imasdb/ITER/3/105027/2",
                "expected_x_shape": (614,),
                "expected_y_shape": (614,),
                "expected_x_unit": "s",
                "expected_y_unit": "Wb",
                "expected_x_label": "magnetics/time",
                "expected_y_label": "flux_loop[0]/flux/data",
                "expected_x_values": [0.002, 150.58029973657193],
                "expected_y_values": [57.9024905871002, 0.5895978890227975],
            },
            # TODO Find relevant public data entry and update test case
            # {
            #     "varname": "magnetics/ip[0]/data",
            #     "pulse": "imas:hdf5?path=/work/imas/shared/imasdb/ITER/3/105027/2",
            #     "expected_x_shape": (108,),
            #     "expected_y_shape": (108,),
            #     "expected_x_unit": "s",
            #     "expected_y_unit": "A",
            #     "expected_x_label": "time",
            #     "expected_y_label": "plasma current",
            #     "expected_x_values": (0.0, 50.0),
            #     "expected_y_values": (-1e7, 1e7)
            # }
        ]

        for test_case in test_cases:
            varname = test_case["varname"]
            pulse = test_case["pulse"]

            with self.subTest(varname=varname, pulse=pulse):
                print(f"* Testing  variable: {varname}")
                print(f"  Pulse: {pulse}")

                dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

                # Use comprehensive validation helper
                self._validate_data_object(
                    dobj,
                    expected_x_shape=test_case.get("expected_x_shape"),
                    expected_y_shape=test_case.get("expected_y_shape"),
                    expected_x_unit=test_case.get("expected_x_unit"),
                    expected_y_unit=test_case.get("expected_y_unit"),
                    expected_x_label=test_case.get("expected_x_label"),
                    expected_y_label=test_case.get("expected_y_label"),
                    expected_x_values=test_case.get("expected_x_values"),
                    expected_y_values=test_case.get("expected_y_values"),
                    varname=varname,
                )

                print(f"  ✓ Test passed for {varname}")

        print("✓ All pulse data access tests passed")

    def test_IMASAccessInvalidVariable(self) -> None:
        """Test IMAS data access with invalid variable name."""
        print("* Testing IMAS access with invalid variable name...")

        varname = "BUIL-SYSM-COM-XX03-BU:SRV6101-NSBPS"
        pulse = "130012/5"

        print(f"Requesting data for variable: {varname}, pulse: {pulse}")
        with self.assertRaises(imas.exception.IDSNameError) as cm:
            dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

            self._validate_data_object(
                dobj,
                expected_x_shape=(0,),
                expected_y_shape=(0,),
                varname=varname,
            )

        print("✓ Test passed: Invalid variable correctly returned empty data")

    def test_IMASAccessNoData(self) -> None:
        """Test IMAS data access when no data is available."""
        print("* Testing IMAS access when no data is available...")

        varname = "UTIL-HV-M1:TS2000-QT01"
        pulse = "12/4"

        print(f"Requesting data for variable: {varname}, pulse: {pulse}")
        dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

        self._validate_data_object(
            dobj,
            expected_x_shape=(0,),
            expected_y_shape=(0,),
            varname=varname,
        )

        print("✓ Test passed: No data scenario correctly returned empty data")

    def test_IMASAccessByPulseWithTime(self) -> None:
        """Test IMAS data access by pulse with time range specification."""
        print("* Testing IMAS access by pulse with time range...")

        varname = "summary/fusion/power/value"
        pulse = "130012/5"
        tsS = "5"
        tsE = "20"

        print(f"Requesting data for variable: {varname}")
        print(f"Pulse: {pulse}, Time range: {tsS}s to {tsE}s")

        dobj = self.da.get_data(
            self.ds, varname=varname, pulse=pulse, tsS=tsS, tsE=tsE, nbp=-1
        )

        self._validate_data_object(
            dobj,
            expected_x_shape=(4,),
            expected_y_shape=(4,),
            expected_x_unit="s",
            expected_y_unit="W",
            expected_x_label="summary/time",
            expected_y_label="fusion/power/value",
            expected_x_values=[
                5.21223,
                16.348919999999993,
            ],
            expected_y_values=[480.217585729846, 616.5169652647418],
            varname=varname,
        )

        print("✓ Test passed: Time range filtering works correctly")

    def test_IMASHeterogenousTimestamp(self) -> None:
        """Test IMAS data access with heterogeneous timestamp data."""
        print("* Testing IMAS access with heterogeneous timestamp...")

        varname = "pulse_schedule/ec/launcher(0)/power/reference/data"
        pulse = "105023/1"

        print(f"Requesting data for variable: {varname}, pulse: {pulse}")
        dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

        self._validate_data_object(
            dobj,
            expected_x_shape=(14,),
            expected_y_shape=(14,),
            expected_x_unit="s",
            expected_y_unit="mixed",
            expected_x_label="pulse_schedule/ec/launcher/power/reference/time",
            expected_y_label="ec/launcher(0)/power/reference/data",
            expected_x_values=[0.0, 6289.0],
            expected_y_values=(0.0, 0.0),
            varname=varname,
        )

        print("✓ Test passed: Heterogeneous timestamp data handled correctly")

    def test_IMASAccessByPulseContourData(self) -> None:
        """Test IMAS data access for contour/profile data."""
        print("* Testing IMAS access for contour/profile data...")

        print("* Testing  2D profile data (PSI contour)...")
        varname1 = "equilibrium/time_slice[0]/profiles_2d[0]/psi"
        varname2 = "equilibrium/time_slice[0]/profiles_2d[0]/r"
        varname3 = "equilibrium/time_slice[0]/profiles_2d[0]/z"
        pulse1 = "135011/7"

        print(f"  Requesting 2D data for variable: {varname1}, pulse: {pulse1}")
        dobj1 = self.da.get_data(self.ds, varname=varname1, pulse=pulse1, nbp=-1)
        dobj2 = self.da.get_data(self.ds, varname=varname2, pulse=pulse1, nbp=-1)
        dobj3 = self.da.get_data(self.ds, varname=varname3, pulse=pulse1, nbp=-1)

        # Validate 2D contour data
        self._validate_data_object(
            dobj1,
            expected_x_shape=(65,),
            expected_y_shape=(65, 129),
            expected_x_unit="mixed",
            expected_y_unit="Wb",
            expected_x_label="equilibrium/time_slice/profiles_2d/grid/dim1",
            expected_y_label="time_slice[0]/profiles_2d[0]/psi",
            expected_x_values=[3.0, 9.0],
            expected_y_values=[0.0, 0.0],
            varname=varname1,
        )

        self._validate_data_object(
            dobj2,
            expected_x_shape=(65,),
            expected_y_shape=(65, 129),
            expected_x_unit="mixed",
            expected_y_unit="m",
            expected_x_label="equilibrium/time_slice/profiles_2d/grid/dim1",
            expected_y_label="time_slice[0]/profiles_2d[0]/r",
            expected_x_values=[3.0, 9.0],
            expected_y_values=[3.0, 9.0],
            varname=varname2,
        )

        self._validate_data_object(
            dobj3,
            expected_x_shape=(65,),
            expected_y_shape=(65, 129),
            expected_x_unit="mixed",
            expected_y_unit="m",
            expected_x_label="equilibrium/time_slice/profiles_2d/grid/dim1",
            expected_y_label="time_slice[0]/profiles_2d[0]/z",
            expected_x_values=[3.0, 9.0],
            expected_y_values=[-6.0, 6.0],
            varname=varname3,
        )
        print("  ✓ 2D profile data test passed")

    def test_IMASAccessTimeRange(self) -> None:
        print("* Testing  1D profile data with time range...")
        tsS = "5"
        tsE = "20"
        varname1 = "core_profiles/time"
        varname2 = "core_profiles/profiles_1d[0]/electrons/temperature"
        pulse2 = "135011/7"

        print(f"  Requesting 1D data with time range: {tsS}s to {tsE}s")
        dobj0 = self.da.get_data(
            self.ds, varname=varname1, tsS=tsS, tsE=tsE, pulse=pulse2, nbp=-1
        )

        dobj1 = self.da.get_data(
            self.ds, varname=varname2, tsS=tsS, tsE=tsE, pulse=pulse2, nbp=-1
        )

        dobj2 = self.da.get_data(
            self.ds, varname=varname2, tsS=tsS, pulse=pulse2, nbp=-1
        )

        dobj3 = self.da.get_data(
            self.ds, varname=varname2, tsE=tsE, pulse=pulse2, nbp=-1
        )

        self._validate_data_object(
            dobj0,
            expected_x_shape=(15,),
            expected_y_shape=(15,),
            expected_x_unit="",
            expected_y_unit="s",
            expected_x_label="",
            expected_y_label="time",
            expected_x_values=[0, 14],
            expected_y_values=[5.927597812055124, 19.927597812055122],
            varname=varname2,
        )

        self._validate_data_object(
            dobj1,
            expected_x_shape=(50,),
            expected_y_shape=(50,),
            expected_x_unit="-",
            expected_y_unit="eV",
            expected_x_label="core_profiles/profiles_1d/grid/rho_tor_norm",
            expected_y_label="profiles_1d[0]/electrons/temperature",
            expected_x_values=(0.0, 0.9963894549516938),
            expected_y_values=(1944.2012301161187, 25.0),
            varname=varname2,
        )

        self._validate_data_object(
            dobj2,
            expected_x_shape=(50,),
            expected_y_shape=(50,),
            expected_x_unit="-",
            expected_y_unit="eV",
            expected_x_label="core_profiles/profiles_1d/grid/rho_tor_norm",
            expected_y_label="profiles_1d[0]/electrons/temperature",
            expected_x_values=(0.0, 0.9963894549516938),
            expected_y_values=(1944.2012301161187, 25.0),
            varname=varname2,
        )

        self._validate_data_object(
            dobj3,
            expected_x_shape=(50,),
            expected_y_shape=(50,),
            expected_x_unit="-",
            expected_y_unit="eV",
            expected_x_label="core_profiles/profiles_1d/grid/rho_tor_norm",
            expected_y_label="profiles_1d[0]/electrons/temperature",
            expected_x_values=(0.0, 0.9963894549516938),
            expected_y_values=(956.471, 10.0),
            varname=varname2,
        )

        print("  ✓ Time-filtered 1D profile data test passed")

        print("✓ All 1D profile data with time range data tests passed")

    def test_IMASAccessDataConsistency(self) -> None:
        """Test data consistency and error handling."""
        print("* Testing IMAS data consistency and error handling...")

        # Test consistent data shapes
        varname = "magnetics/flux_loop[0]/flux/data"
        pulse = "imas:hdf5?path=/work/imas/shared/imasdb/ITER/3/105027/2"

        print(f"* Testing data consistency for: {varname}")
        dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

        # Ensure X and Y data have consistent shapes for time series data
        if hasattr(dobj, "xdata") and hasattr(dobj, "ydata"):
            x_shape = np.shape(dobj.xdata)
            y_shape = np.shape(dobj.ydata)

            if len(x_shape) == 1 and len(y_shape) == 1:
                self.assertEqual(
                    x_shape[0],
                    y_shape[0],
                    f"X and Y data should have same length for time series. X: {x_shape}, Y: {y_shape}",
                )
                print(
                    f"  ✓ Data consistency check passed: X{x_shape} matches Y{y_shape}"
                )

            # Check for valid data ranges
            if isinstance(dobj.xdata, np.ndarray) and dobj.xdata.size > 0:
                self.assertFalse(
                    np.any(np.isnan(dobj.xdata)), "X data should not contain NaN values"
                )
                self.assertFalse(
                    np.any(np.isinf(dobj.xdata)),
                    "X data should not contain infinite values",
                )
                print("  ✓ X data validity check passed")

        print("✓ Data consistency tests passed")

    def test_IMASAccessSingleTimeSlice(self) -> None:
        """Test IMAS for single time slice"""
        print("* Testing IMAS for single time slice...")

        varname = "equilibrium/time_slice[5]/profiles_2d[0]/psi"
        pulse = "135011/7"

        print(f"VARIABLE: {varname}")
        dobj = self.da.get_data(self.ds, varname=varname, pulse=pulse, nbp=-1)

        self._validate_data_object(
            dobj,
            expected_x_shape=(65,),
            expected_y_shape=(65, 129),
            expected_x_unit="mixed",
            expected_y_unit="Wb",
            expected_x_label="equilibrium/time_slice/profiles_2d/grid/dim1",
            expected_y_label="time_slice[5]/profiles_2d[0]/psi",
            expected_x_values=[3.0, 9.0],
            expected_y_values=(0.0, 0.0),
            varname=varname,
        )
        print("✓ Single time slice test passed")

        print("* Testing  1D profile data (electron temperature)...")
        varname2 = "core_profiles/profiles_1d[0]/electrons/temperature"
        pulse2 = "135011/7"

        print(f"  Requesting 1D data for variable: {varname2}, pulse: {pulse2}")
        dobj2 = self.da.get_data(self.ds, varname=varname2, pulse=pulse2, nbp=-1)

        self._validate_data_object(
            dobj2,
            expected_x_shape=(50,),
            expected_y_shape=(50,),
            expected_x_unit="-",
            expected_y_unit="eV",
            expected_x_label="core_profiles/profiles_1d/grid/rho_tor_norm",
            expected_y_label="profiles_1d[0]/electrons/temperature",
            expected_x_values=[0.0, 0.9963894549516938],
            expected_y_values=[956.471, 10.0],
            varname=varname2,
        )

        print("  ✓ 1D profile data test passed")

    def test_IMASAccessAllTimeSlices(self) -> None:
        """Test IMAS for all time slices"""
        print("* Testing IMAS for all time slices...")

        varname1 = "equilibrium/time_slice[:]/profiles_2d[0]/psi"
        pulse1 = "135011/7"

        varname2 = "core_profiles/profiles_1d[:]/electrons/temperature"
        pulse2 = "105027/2"

        varname3 = "magnetics/flux_loop[:]/flux/data"
        pulse3 = "105027/2"

        varname4 = "magnetics/flux_loop[5:10]/flux/data"
        pulse4 = "105027/2"

        print(f"VARIABLE: {varname1}")
        dobj1 = self.da.get_data(self.ds, varname=varname1, pulse=pulse1, nbp=-1)
        print(f"VARIABLE: {varname2}")
        dobj2 = self.da.get_data(self.ds, varname=varname2, pulse=pulse2, nbp=-1)
        print(f"VARIABLE: {varname3}")
        dobj3 = self.da.get_data(self.ds, varname=varname3, pulse=pulse3, nbp=-1)
        print(f"VARIABLE: {varname4}")
        dobj4 = self.da.get_data(self.ds, varname=varname4, pulse=pulse4, nbp=-1)

        self._validate_data_object(
            dobj1,
            expected_x_shape=(986,),
            expected_y_shape=(986, 65, 129),
            expected_x_unit="s",
            expected_y_unit="Wb",
            expected_x_label="time",
            expected_y_label="time_slice[:]/profiles_2d[0]/psi",
            expected_x_values=[0.002, 790.2892644787217],
            expected_y_values=[0.0, -77.93501569800662],
            varname=varname1,
        )

        self._validate_data_object(
            dobj2,
            expected_x_shape=(614,),
            expected_y_shape=(614, 50),
            expected_x_unit="s",
            expected_y_unit="eV",
            expected_x_label="time",
            expected_y_label="profiles_1d[:]/electrons/temperature",
            expected_x_values=[0.002, 150.58029973657193],
            expected_y_values=[956.471, 116.6366274285177],
            varname=varname2,
        )

        self._validate_data_object(
            dobj3,
            expected_x_shape=(24,),
            expected_y_shape=(24, 614),
            expected_x_unit="",
            expected_y_unit="Wb",
            expected_x_label="",
            expected_y_label="flux_loop[:]/flux/data",
            expected_x_values=[0, 23],
            expected_y_values=[57.9024905871002, 0.4646550704933909],
            varname=varname3,
        )

        self._validate_data_object(
            dobj4,
            expected_x_shape=(5,),
            expected_y_shape=(5, 614),
            expected_x_unit="",
            expected_y_unit="Wb",
            expected_x_label="",
            expected_y_label="flux_loop[5:10]/flux/data",
            expected_x_values=[5, 9],
            expected_y_values=[58.86716011367322, 0.3972396311867252],
            varname=varname3,
        )

        print("✓ All time slice test passed")


def suite():
    """Create a test suite for IMAS access tests."""
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestIMASAccess))
    return suite


if __name__ == "__main__":
    print("=" * 70)
    print("Running IMAS Data Access Regression Tests")

    # Configure test runner for verbose output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=None,
        descriptions=True,
        failfast=False,
        buffer=False,
    )
    result = runner.run(suite())

    print("\n" + "=" * 70)
    print("TEST EXECUTION SUMMARY")
    print("=" * 70)

    if result.wasSuccessful():
        print("✓ ALL TESTS PASSED!")
        print(f"Total tests run: {result.testsRun}")
    else:
        print("✗ SOME TESTS FAILED!")
        print(f"Total tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print(f"Skipped: {len(result.skipped)}")

        if result.failures:
            print("\nFAILURES:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")

        if result.errors:
            print("\nERRORS:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")

    print("=" * 70)
