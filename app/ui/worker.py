import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
	finished = Signal()


class Worker(QRunnable):
	def __init__(self, function : Callable[..., Any], *args : Any) -> None:
		super().__init__()
		self.function = function
		self.args = args
		self.result : Any = None
		self.error : Optional[str] = None
		self.signals = WorkerSignals()
		self.setAutoDelete(False)

	def run(self) -> None:
		try:
			self.result = self.function(*self.args)
		except SystemExit as exception:
			self.error = 'Engine stopped with code ' + str(exception.code)
		except Exception as exception:
			traceback.print_exc()
			self.error = str(exception) or type(exception).__name__
		finally:
			self.signals.finished.emit()


class ProgressBridge(QObject):
	progressed = Signal(str, int, int)

	def emit_progress(self, description : str, current : int, total : int) -> None:
		self.progressed.emit(description, current, total)
