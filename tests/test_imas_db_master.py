# Description: Unit tests for the IMASDBMaster YAML scenario loader.

import textwrap

import pandas as pd
import pytest

from iplotDataAccess.imasDBMaster import IMASDBMaster, yaml_mapping


def _write_active_yaml(path, *, shot=12345, run=1, status="active", workflow="HFPS"):
    path.write_text(textwrap.dedent(f"""
        status: {status}
        reference_name: scen-A
        responsible_name: ITER Org
        characteristics:
          shot: {shot}
          run: {run}
          type: standard
          workflow: {workflow}
          machine: ITER
        scenario_key_parameters:
          confinement_regime: H-mode
        plasma_composition:
          species: D T
          n_over_ne: 0.5 0.5
        idslist:
          summary:
            time_step_number: 100
        free_description: test scenario
    """).strip())


class TestGetYamlData:

    def test_returns_loaded_dict(self, tmp_path):
        f = tmp_path / "scenario.yaml"
        _write_active_yaml(f)
        data = IMASDBMaster.get_yaml_data(str(f))
        assert isinstance(data, dict)
        assert data["status"] == "active"

    def test_returns_none_for_missing_file(self, tmp_path):
        assert IMASDBMaster.get_yaml_data(str(tmp_path / "missing.yaml")) is None

    def test_returns_none_for_invalid_yaml(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(":\n  - [unbalanced")
        assert IMASDBMaster.get_yaml_data(str(f)) is None


class TestGetDataFrameFromYaml:

    def test_returns_dataframe_for_active_status(self, tmp_path):
        f = tmp_path / "scenario.yaml"
        _write_active_yaml(f, status="active")
        df = IMASDBMaster.get_data_frame_from_yaml(str(f))
        assert isinstance(df, pd.DataFrame)
        assert df.iloc[0]["characteristics.shot"] == 12345

    def test_returns_none_for_obsolete_status_unless_flagged(self, tmp_path):
        f = tmp_path / "scenario.yaml"
        _write_active_yaml(f, status="obsolete")
        assert IMASDBMaster.get_data_frame_from_yaml(str(f)) is None
        df = IMASDBMaster.get_data_frame_from_yaml(str(f), add_obsolete=True)
        assert isinstance(df, pd.DataFrame)

    def test_returns_none_for_missing_file(self, tmp_path):
        assert IMASDBMaster.get_data_frame_from_yaml(str(tmp_path / "missing.yaml")) is None


class TestGetDataframesFromFiles:

    def test_concatenates_active_yaml_files_recursively(self, tmp_path):
        v3_dir = tmp_path / "ITER" / "3" / "0"
        v4_dir = tmp_path / "ITER" / "4" / "1"
        v3_dir.mkdir(parents=True)
        v4_dir.mkdir(parents=True)
        _write_active_yaml(v3_dir / "a.yaml", shot=1)
        _write_active_yaml(v4_dir / "b.yaml", shot=2)

        master = IMASDBMaster(directory_list=[str(tmp_path)])
        df = master.get_dataframes_from_files()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "pulse" in df.columns
        assert sorted(df["pulse"]) == [1, 2]

    def test_obsolete_files_are_excluded_by_default(self, tmp_path):
        d = tmp_path / "scenarios"
        d.mkdir()
        _write_active_yaml(d / "active.yaml", shot=1, status="active")
        _write_active_yaml(d / "obsolete.yaml", shot=2, status="obsolete")

        master = IMASDBMaster(directory_list=[str(tmp_path)])
        df = master.get_dataframes_from_files()
        assert sorted(df["pulse"]) == [1]

    def test_columns_are_renamed_via_yaml_mapping(self, tmp_path):
        d = tmp_path / "scenarios"
        d.mkdir()
        _write_active_yaml(d / "x.yaml")

        master = IMASDBMaster(directory_list=[str(tmp_path)])
        df = master.get_dataframes_from_files()
        renamed_columns = set(yaml_mapping.values())
        present = renamed_columns.intersection(df.columns)
        assert "pulse" in present
        assert "ref_name" in present


class TestExtractInformation:

    def test_species_composition_is_built_and_sorted(self, tmp_path):
        d = tmp_path / "scenarios"
        d.mkdir()
        _write_active_yaml(d / "scenario.yaml")

        master = IMASDBMaster(directory_list=[str(tmp_path)])
        df = master.get_dataframes_from_files()
        composition = df.iloc[0]["composition"]
        assert "D" in composition
        assert "T" in composition
        assert "(0.5)" in composition

    def test_composition_falls_back_to_none_string_when_species_missing(self, tmp_path):
        d = tmp_path / "scenarios"
        d.mkdir()
        (d / "no_species.yaml").write_text(textwrap.dedent("""
            status: active
            reference_name: scen-B
            characteristics:
              shot: 999
              run: 1
            idslist:
              summary:
                time_step_number: 50
        """).strip())

        master = IMASDBMaster(directory_list=[str(tmp_path)])
        df = master.get_dataframes_from_files()
        assert df.iloc[0]["composition"] == "None"
