from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

DS_CODAC_TYPE = "CODAC_UDA"
DS_IMAS_TYPE = "IMAS_UDA"
DS_CSV_TYPE = "CSV"


class DataSourceConfig:

    def __init__(self, parent=None):
        self.supportedDataSources = []

    def get_supported_data_source(self):
        # Check CODAC UDA module is installed
        try:
            import uda_client_reader
            logger.info("module 'uda client reader' is installed")

            import iplotDataAccess.udaAccess
            logger.info("module 'uda client' is installed")
            self.supportedDataSources.append(DS_CODAC_TYPE)
        except ModuleNotFoundError:
            logger.error("module 'uda client' is not installed")

        try:
            import imas
            import iplotDataAccess.imasAccess
            logger.info("module imas is installed")
            self.supportedDataSources.append(DS_IMAS_TYPE)
        except ModuleNotFoundError:
            logger.error("module 'imas' is not installed")
        try:
            import sseclient
            logger.info("module sseclient is installed")
        except ModuleNotFoundError:
            logger.error("module 'sseclient' is not installed")

        try:
            import iplotDataAccess.csvAccess
            self.supportedDataSources.append(DS_CSV_TYPE)
        except ModuleNotFoundError:
            logger.error("module 'csvAccess' is not installed")

        return self.supportedDataSources
