from iplotDataAccess.dataAccess import DataAccess
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)


class AppDataAccess:
    da: DataAccess = None
    configured: bool = False

    # ---------------

    @staticmethod
    def initialize(config_file=None, source_types=None):
        """Load the data sources of `config_file`, or of the file DataAccess.load_config() finds; only those
        of `source_types` if given. The data access object, and the types it loads, are made on the first call."""
        if AppDataAccess.da is None:
            AppDataAccess.da = DataAccess(source_types)
        AppDataAccess.configured = AppDataAccess.da.load_config(config_file)
        return AppDataAccess.configured

    @staticmethod
    def get_data_access():
        return AppDataAccess.da

    @staticmethod
    def is_configured():
        return AppDataAccess.configured
