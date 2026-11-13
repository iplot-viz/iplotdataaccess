"""Cancelling the read in progress of a data source (DataSource.cancel), and the export files a stopped export leaves.

A stand-in for the UDA reader blocks its fetch until cancelAPI() is called, as the UDA clients that can cancel do, so
no UDA server is needed.
"""
import threading
from unittest.mock import patch

import numpy as np
import pyarrow.parquet as pq
import pytest

pytest.importorskip("uda_client_reader.uda_client_reader_python", reason="uda_client_reader package required")

from iplotDataAccess.dataAccess import DataAccess
from iplotDataAccess.dataCommon import ReadCancelled
from iplotDataAccess.udaAccess import UdaAccess

START = 1_648_771_200_000_000_000
QUERY = dict(varname="VAR", tsS=str(START), tsE=str(START + 60_000_000_000), tsFormat="absolute", nbp=1000)


class _Reader:
    """Fetches return at once, or, with `block`, once cancelAPI() is called, with the error of a read it stopped."""

    def __init__(self, block=False):
        self.block = block
        self.fetches = 0
        self.fetching = threading.Event()
        self.cancelled = threading.Event()

    def fetchData(self, query):
        self.fetches += 1
        if self.block:
            self.fetching.set()
            assert self.cancelled.wait(10)
            return -1
        return 0

    def cancelAPI(self):
        self.cancelled.set()

    def getErrorMsg(self):
        return "No Data waiting at Socket when Data Expected!"

    def resetAll(self):
        pass

    def releaseData(self, handle):
        pass

    def getFetchedTimeType(self, handle):
        return None

    def getFetchedType(self, handle):
        return None

    def getLabelX(self, handle):
        return "Time"

    def getLabelY(self, handle):
        return "VAR"

    def getUnitsY(self, handle):
        return "V"

    def getRank(self, handle):
        return 1

    def getDataNativeRank(self, handle):
        return np.arange(3.0)

    def getTimeStampsAsLong(self, handle):
        return np.arange(START, START + 3, dtype=np.int64)


def _source(reader) -> UdaAccess:
    source = UdaAccess("uda", {"host": "nowhere", "port": 3090})
    source.UCR = reader
    source.connected = True
    return source


def test_a_cancelled_read_raises_and_leaves_nothing_in_the_cache():
    reader = _Reader(block=True)
    source = _source(reader)
    outcome = {}

    def read():
        try:
            source.get_data(**QUERY)
        except ReadCancelled as e:
            outcome['error'] = e

    thread = threading.Thread(target=read)
    thread.start()
    assert reader.fetching.wait(10)
    assert source.cancel()
    thread.join(10)

    assert isinstance(outcome.get('error'), ReadCancelled)
    reader.block = False
    data = source.get_data(**QUERY)
    assert data.errcode == 0
    assert reader.fetches == 2


def test_a_read_that_fails_without_a_cancel_gives_its_error():
    reader = _Reader()
    reader.fetchData = lambda query: -1
    data = _source(reader).get_data(**QUERY)
    assert data.errcode == -1


def test_a_cancel_between_reads_leaves_the_next_read_alone():
    reader = _Reader()
    source = _source(reader)
    assert source.cancel()
    assert source.get_data(**QUERY).errcode == 0


def test_a_uda_client_that_cannot_cancel_lets_the_read_end():
    assert not _source(object()).cancel()


def test_data_access_cancels_the_reads_of_its_data_sources_that_can():
    data_access = DataAccess()
    able, unable = _source(_Reader()), _source(object())
    data_access.ds_list = {"able": able, "unable": unable, "missing": None}
    assert data_access.cancel()
    assert able.UCR.cancelled.is_set()
    data_access.ds_list = {"unable": unable}
    assert not data_access.cancel()


def test_an_export_stopped_between_variables_leaves_its_file_closed(tmp_path):
    from iplotDataAccess.dataHandling.exportData import exportData

    class Stop(Exception):
        pass

    def progress(name):
        if name == "B":
            raise Stop()

    target = tmp_path / "out.parquet"
    exportData.relative_start_ns = None
    with patch.object(exportData.UdaClientIterator, "readDataChunk", lambda *args: None):
        with pytest.raises(Stop):
            exportData.extractAndGenerateParquet({"A": "", "B": ""}, _source(_Reader()), None, START, START + 1,
                                                 str(target),
                                                 progressCallback=progress)
    assert pq.read_table(str(target)).num_rows == 0
    target.unlink()
