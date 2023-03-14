from iplotDataAccess.dataAccess import DataAccess
import iplotLogging.setupLogger as ls
import os

logger = ls.get_logger(__name__)

class AppDataAccess:
    da = None
    configured = False

    # ---------------

    @staticmethod
    def loadConfiguration(configFile=None):
        if AppDataAccess.da is None:
            AppDataAccess.da = DataAccess()
        AppDataAccess.configured=AppDataAccess.da.loadConfig(configFile)
        return AppDataAccess.configured

    @staticmethod
    def getDataAccess():
        return AppDataAccess.da

    @staticmethod
    def isConfigured():
        return AppDataAccess.configured