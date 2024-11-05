from iplotDataAccess.dataAccess import DataAccess
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)


class AppDataAccess:
    da: DataAccess = None
    configured: bool = False

    # ---------------

    @staticmethod
    def initialize(config_file=None):
        if AppDataAccess.da is None:
            AppDataAccess.da = DataAccess()
        AppDataAccess.configured = AppDataAccess.da.load_config(config_file)
        return AppDataAccess.configured

    @staticmethod
    def get_data_access():
        return AppDataAccess.da

    @staticmethod
    def is_configured():
        return AppDataAccess.configured
