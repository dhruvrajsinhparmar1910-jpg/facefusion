import os
import subprocess
import sys
from typing import Any

from app.settings import get_data_directory


def get_base_directory() -> str:
	if getattr(sys, 'frozen', False):
		return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
	return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def redirect_output() -> None:
	if sys.stdout is None or sys.stderr is None:
		log_directory = os.path.join(get_data_directory(), 'logs')
		os.makedirs(log_directory, exist_ok = True)
		log_file = open(os.path.join(log_directory, 'app.log'), 'a', encoding = 'utf-8', buffering = 1)
		sys.stdout = sys.stdout or log_file
		sys.stderr = sys.stderr or log_file


def hide_console_windows() -> None:
	if os.name == 'nt':
		popen_class = subprocess.Popen

		class HiddenPopen(popen_class): # type:ignore[valid-type, misc]
			def __init__(self, *args : Any, **kwargs : Any) -> None:
				kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW # type:ignore[attr-defined]
				if kwargs.get('stdin') is None:
					kwargs['stdin'] = subprocess.DEVNULL
				super().__init__(*args, **kwargs)

		subprocess.Popen = HiddenPopen # type:ignore[misc]


def prepare_environment() -> None:
	base_directory = get_base_directory()
	ffmpeg_directory = os.path.join(base_directory, 'ffmpeg')

	os.environ['OMP_NUM_THREADS'] = '1'
	if os.path.isdir(ffmpeg_directory):
		os.environ['PATH'] = ffmpeg_directory + os.pathsep + os.environ.get('PATH', '')
	redirect_output()
	hide_console_windows()
	os.chdir(base_directory)


def self_test(report_path : str) -> int:
	import tempfile

	from app import engine
	from app.settings import Settings

	lines = []
	missing_dependencies = engine.check_dependencies()
	lines.append('dependencies missing: ' + (', '.join(missing_dependencies) or 'none'))

	if not missing_dependencies:
		from facefusion import core, state_manager
		from facefusion.processors.core import get_processors_modules

		engine.bootstrap(Settings(models_path = os.path.join(tempfile.gettempdir(), 'FaceSwap-self-test-models')))
		processor_modules = get_processors_modules(state_manager.get_item('processors'))
		lines.append('device: ' + engine.get_active_device())
		lines.append('processors: ' + ', '.join(module.__name__ for module in processor_modules))
		lines.append('content analyser check: ' + str(core.common_pre_check()))

	success = not missing_dependencies and lines[-1].endswith('True')
	lines.append('self test: ' + ('passed' if success else 'failed'))

	with open(report_path, 'w', encoding = 'utf-8') as report_file:
		report_file.write('\n'.join(lines) + '\n')
	return 0 if success else 1


def main() -> int:
	report_path = None

	if '--self-test' in sys.argv:
		report_index = sys.argv.index('--self-test') + 1
		report_path = os.path.abspath(sys.argv[report_index] if report_index < len(sys.argv) else os.path.join(get_data_directory(), 'self-test.txt'))
	prepare_environment()

	if report_path:
		return self_test(report_path)

	from PySide6.QtGui import QIcon
	from PySide6.QtWidgets import QApplication

	from app.settings import load_settings
	from app.ui.main_window import MainWindow

	application = QApplication(sys.argv)
	application.setApplicationName('FaceSwap')
	application.setOrganizationName('FaceSwap')
	application.setStyle('Fusion')
	icon_path = os.path.join(get_base_directory(), 'facefusion.ico')
	if os.path.isfile(icon_path):
		application.setWindowIcon(QIcon(icon_path))

	window = MainWindow(load_settings())
	window.show()
	return application.exec()


if __name__ == '__main__':
	sys.exit(main())
