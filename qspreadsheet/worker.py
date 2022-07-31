import logging
import os
import sys
from types import TracebackType
from typing import Callable, Tuple, Type

from PySide2.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    
    about_to_start = Signal()
    result = Signal(object)
    error = Signal(tuple) # Tuple[Type[BaseException], BaseException, TracebackType]
    finished = Signal()
    progress = Signal(int, str)


class Worker(QRunnable):
    
    def __init__(self, func: Callable, *args, **kwargs) -> None:
        super(Worker, self).__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    def run(self) -> None:
        try:
            self.signals.about_to_start.emit()
            result = self.func(*self.args, **self.kwargs)
        except:
            self.signals.error.emit(sys.exc_info())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()