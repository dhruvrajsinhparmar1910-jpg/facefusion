import importlib
from typing import Any, Callable, Optional

from tqdm import tqdm

ProgressCallback = Callable[[str, int, int], None]

PROGRESS_CALLBACK : Optional[ProgressCallback] = None
PATCHED_MODULES =\
[
	'facefusion.content_analyser',
	'facefusion.download',
	'facefusion.ffmpeg',
	'facefusion.workflows.to_video'
]


class NullWriter:
	def write(self, text : str) -> int:
		return len(text)

	def flush(self) -> None:
		pass


class BridgeTqdm(tqdm): # type:ignore[type-arg]
	def __init__(self, *args : Any, **kwargs : Any) -> None:
		kwargs['disable'] = False
		kwargs['file'] = NullWriter()
		super().__init__(*args, **kwargs)
		emit_progress(self.desc, self.n, self.total)

	def update(self, n : float = 1) -> Optional[bool]:
		result = super().update(n)
		emit_progress(self.desc, self.n, self.total)
		return result


def emit_progress(description : str, current : float, total : Optional[float]) -> None:
	if PROGRESS_CALLBACK:
		PROGRESS_CALLBACK(description or '', int(current or 0), int(total or 0))


def set_progress_callback(progress_callback : Optional[ProgressCallback]) -> None:
	global PROGRESS_CALLBACK

	PROGRESS_CALLBACK = progress_callback


def install() -> None:
	for module_name in PATCHED_MODULES:
		module = importlib.import_module(module_name)
		setattr(module, 'tqdm', BridgeTqdm)
