import time
from functools import partial
from threading import Thread

import numpy as np


# CWS-SCSU-0000:CU510{1,2,3,4}-TT-XI, CTRL-SYSM-CUB-4505-61:CU000{1,2,3}-HTH-TT,BUIL-B36-VA-RT-RT1:CL0001-TT02-STATE
# CTRL-SYSM-CUB-4505-61:CU0001-HTH-TT

#TODO: Move to access
class CanvasStreamer:

    def __init__(self, da):
        self.da = da
        self.stop_flag = False
        self.signals = {}
        self.collectors = []
        self.streamers = []

    def start(self, canvas, callback):
        self.stop_flag = False
        all_signals = []
        for col in canvas.plots:
            for plot in col:
                for (stack_id, signals) in plot.signals.items():
                    all_signals += signals

        self.signals = {s.varname:s for s in all_signals}

        signals_by_ds = dict()
        for s in all_signals:
            if signals_by_ds.get(s.datasource):
                signals_by_ds[s.datasource].append(s.varname)
            else:
                signals_by_ds[s.datasource]=[s.varname]

        for ds in signals_by_ds.keys():
            print("Starting streamer for ",ds)
            self.start_stream(ds, signals_by_ds[ds], partial(self.handler, callback))

    def start_stream(self, ds, varnames, callback):
        collect_thread = Thread(name="collector", target=self.stream_thread, args=(ds, varnames, callback))
        collect_thread.start()
        self.collectors.append(collect_thread)

    def stream_thread(self, ds, varnames, callback):
        print("STREAM START", varnames,ds,self.da.startSubscription)
        streaming_thread = Thread(name="receiver", target=self.da.startSubscription, args=(ds,), kwargs={'params':varnames})
        streaming_thread.start()
        self.streamers.append(streaming_thread)

        while not self.stop_flag:
            for varname in varnames:
                dobj = self.da.getNextData(ds, varname)

                if dobj is not None and dobj.xdata is not None and len(dobj.xdata) > 0 and callback is not None:
                    callback(varname,dobj)
            time.sleep(0.1)

        print("Issuing stop subscription...")

        # self.da.stopSubscription(ds)
        stopping_thread = Thread(name="stopper", target=self.da.stopSubscription, args=(ds,))
        stopping_thread.start()


    def stop(self):
        self.stop_flag = True
        self.collectors.clear()
        self.streamers.clear()

    def handler(self,callback, varname, dobj):
        signal = self.signals.get(varname)
        if signal:
            signal.data_hash = signal.calculate_data_hash()
            data = signal.get_data()
            print("\tUPDATED {} with {} new samples".format(varname,len(dobj.xdata)))
            xdata = np.append(data[0], dobj.xdata)
            ydata = np.append(data[1], dobj.ydata)
            signal.set_data([xdata,ydata])
            signal.units = [dobj.xunit, dobj.yunit]
            callback(signal)

