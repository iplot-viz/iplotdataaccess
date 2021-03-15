import iplotlib.log.setupLogger as ls
logger = ls.get_logger(__name__)
class dataSourceConfig:

    def __init__(self,parent=None):
        self.supportedDataSources=[]

    def getSupportedDataSource(self):
        ##check CODAC UDA module is installed
        try:
            import uda_client_reader
            import iplotlib.access.udaAccess
            logger.info("module 'uda client' is installed")
            self.supportedDataSources.append("CODAC_UDA")
        except ModuleNotFoundError:
            logger.error("module 'uda client' is not installed")

        try:
            import imas
            import iplotlib.access.imasAccess
            logger.info("module imas is installed")
            self.supportedDataSources.append("IMAS_UDA")
        except ModuleNotFoundError:
            logger.error("module 'imas' is not installed")
        return self.supportedDataSources
