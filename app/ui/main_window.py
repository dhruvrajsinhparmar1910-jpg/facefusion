import os
from typing import Any, Callable, List, Optional, Set, Tuple

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app import engine, media, progress
from app.settings import Settings, save_settings
from app.ui.widgets import ImageView
from app.ui.worker import ProgressBridge, Worker

SOURCE_FILTER = 'Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)'


class SidePanel(QWidget):
	changed = Signal()

	def __init__(self, settings : Settings) -> None:
		super().__init__()
		self.settings = settings
		self.source_paths : List[str] = []
		layout = QVBoxLayout(self)

		source_group = QGroupBox('Source face')
		source_layout = QVBoxLayout(source_group)
		self.source_view = ImageView('Drop your face photo here', media.IMAGE_EXTENSIONS)
		self.source_view.files_dropped.connect(self.set_source_paths)
		source_browse_button = QPushButton('Choose photo...')
		source_browse_button.clicked.connect(self.browse_source)
		source_layout.addWidget(self.source_view, 1)
		source_layout.addWidget(source_browse_button)
		layout.addWidget(source_group, 1)

		options_group = QGroupBox('Options')
		options_layout = QFormLayout(options_group)
		self.swapper_combo = QComboBox()
		for model_name, model_label in engine.FACE_SWAPPER_MODELS:
			self.swapper_combo.addItem(model_label, model_name)
		self.select_combo_data(self.swapper_combo, settings.face_swapper_model)
		self.enhancer_check = QCheckBox('Face enhancer')
		self.enhancer_check.setChecked(settings.face_enhancer_enabled)
		self.enhancer_combo = QComboBox()
		for model_name, model_label in engine.FACE_ENHANCER_MODELS:
			self.enhancer_combo.addItem(model_label, model_name)
		self.select_combo_data(self.enhancer_combo, settings.face_enhancer_model)
		self.enhancer_combo.setEnabled(settings.face_enhancer_enabled)
		self.occlusion_check = QCheckBox('Occlusion mask (hands, hair, glasses)')
		self.occlusion_check.setChecked(settings.occlusion_mask_enabled)
		options_layout.addRow('Swapper', self.swapper_combo)
		options_layout.addRow(self.enhancer_check)
		options_layout.addRow('Enhancer', self.enhancer_combo)
		options_layout.addRow(self.occlusion_check)
		layout.addWidget(options_group)

		self.swapper_combo.currentIndexChanged.connect(self.store_options)
		self.enhancer_check.toggled.connect(self.store_options)
		self.enhancer_combo.currentIndexChanged.connect(self.store_options)
		self.occlusion_check.toggled.connect(self.store_options)

	@staticmethod
	def select_combo_data(combo : QComboBox, data : str) -> None:
		index = combo.findData(data)
		combo.setCurrentIndex(max(0, index))

	def browse_source(self) -> None:
		paths, _ = QFileDialog.getOpenFileNames(self, 'Choose source face', '', SOURCE_FILTER)
		if paths:
			self.set_source_paths(paths)

	def set_source_paths(self, paths : List[str]) -> None:
		self.source_paths = [ path for path in paths if media.is_image_file(path) ]
		if self.source_paths:
			self.source_view.set_pixmap(QPixmap(self.source_paths[0]))
		else:
			self.source_view.clear_image()
		self.changed.emit()

	def store_options(self) -> None:
		self.enhancer_combo.setEnabled(self.enhancer_check.isChecked())
		self.settings.face_swapper_model = self.swapper_combo.currentData()
		self.settings.face_enhancer_enabled = self.enhancer_check.isChecked()
		self.settings.face_enhancer_model = self.enhancer_combo.currentData()
		self.settings.occlusion_mask_enabled = self.occlusion_check.isChecked()
		save_settings(self.settings)
		self.changed.emit()

	def create_options(self, target_path : str, output_path : str = '') -> engine.SwapOptions:
		return engine.SwapOptions(
			source_paths = list(self.source_paths),
			target_path = target_path,
			output_path = output_path,
			face_swapper_model = self.settings.face_swapper_model,
			face_enhancer_enabled = self.settings.face_enhancer_enabled,
			face_enhancer_model = self.settings.face_enhancer_model,
			occlusion_mask_enabled = self.settings.occlusion_mask_enabled
		)


class MainWindow(QMainWindow):
	busy_changed = Signal(bool)
	cancel_requested = Signal()
	ready_changed = Signal(bool)

	def __init__(self, settings : Settings) -> None:
		super().__init__()
		self.settings = settings
		self.engine_ready = False
		self.busy = False
		self.workers : Set[Worker] = set()
		self.thread_pool = QThreadPool()
		self.thread_pool.setMaxThreadCount(1)
		self.progress_bridge = ProgressBridge()
		self.progress_bridge.progressed.connect(self.update_progress)

		self.setWindowTitle('FaceSwap')
		self.resize(1280, 820)
		self.create_menu()

		self.side_panel = SidePanel(settings)
		self.tabs = QTabWidget()
		self.create_tabs()

		splitter = QSplitter()
		splitter.addWidget(self.side_panel)
		splitter.addWidget(self.tabs)
		splitter.setStretchFactor(0, 0)
		splitter.setStretchFactor(1, 1)
		splitter.setSizes([ 300, 980 ])

		self.status_label = QLabel('Starting engine...')
		self.progress_bar = QProgressBar()
		self.progress_bar.setTextVisible(True)
		self.cancel_button = QPushButton('Cancel')
		self.cancel_button.setEnabled(False)
		self.cancel_button.clicked.connect(self.cancel)
		self.device_label = QLabel('')

		bottom_layout = QHBoxLayout()
		bottom_layout.addWidget(self.status_label, 2)
		bottom_layout.addWidget(self.progress_bar, 3)
		bottom_layout.addWidget(self.cancel_button)
		bottom_layout.addWidget(self.device_label)

		central = QWidget()
		central_layout = QVBoxLayout(central)
		central_layout.addWidget(splitter, 1)
		central_layout.addLayout(bottom_layout)
		self.setCentralWidget(central)

		self.start_engine()

	def create_menu(self) -> None:
		file_menu = self.menuBar().addMenu('&File')
		settings_action = QAction('&Settings...', self)
		settings_action.triggered.connect(self.open_settings)
		output_action = QAction('Open &output folder', self)
		output_action.triggered.connect(self.open_output_folder)
		quit_action = QAction('&Quit', self)
		quit_action.triggered.connect(self.close)
		file_menu.addAction(settings_action)
		file_menu.addAction(output_action)
		file_menu.addSeparator()
		file_menu.addAction(quit_action)

	def create_tabs(self) -> None:
		from app.ui.batch_tab import BatchTab
		from app.ui.swap_tab import SwapTab

		self.tabs.addTab(SwapTab(self, 'image'), 'Image')
		self.tabs.addTab(SwapTab(self, 'gif'), 'GIF')
		self.tabs.addTab(SwapTab(self, 'video'), 'Video')
		self.tabs.addTab(BatchTab(self), 'Batch')

	def start_engine(self) -> None:
		missing_dependencies = engine.check_dependencies()

		if missing_dependencies:
			QMessageBox.critical(self, 'Missing dependencies', 'Not found on PATH: ' + ', '.join(missing_dependencies))
			self.status_label.setText('Missing: ' + ', '.join(missing_dependencies))
			return

		self.run_task(self.bootstrap_engine, (), self.on_engine_ready, busy_text = 'Starting engine...', require_ready = False)

	def bootstrap_engine(self) -> str:
		engine.bootstrap(self.settings)
		progress.install()
		progress.set_progress_callback(self.progress_bridge.emit_progress)
		return engine.get_active_device()

	def on_engine_ready(self, device : str) -> None:
		self.engine_ready = True
		self.update_device_label(device)
		self.status_label.setText('Ready. Models are stored in ' + self.settings.get_models_path())
		self.ready_changed.emit(True)
		self.check_models()

	def check_models(self) -> None:
		options = self.side_panel.create_options('')
		self.run_task(engine.prepare_models, (options,), self.on_models_checked, busy_text = 'Checking models (first run downloads them)...')

	def on_models_checked(self, success : bool) -> None:
		if success:
			self.status_label.setText('Ready')
		else:
			self.show_error('Model download failed: ' + engine.pop_error_message())

	def update_device_label(self, device : str) -> None:
		self.device_label.setText('GPU (CUDA)' if device == 'cuda' else 'CPU')
		self.device_label.setToolTip('Low VRAM mode' if self.settings.low_vram else '')

	def run_task(self, function : Callable[..., Any], args : Tuple[Any, ...], on_success : Optional[Callable[[Any], None]] = None, on_failure : Optional[Callable[[str], None]] = None, busy_text : str = 'Working...', cancellable : bool = False, require_ready : bool = True) -> bool:
		if self.busy or (require_ready and not self.engine_ready):
			return False

		worker = Worker(function, *args)
		self.workers.add(worker)
		self.set_busy(True, busy_text, cancellable)
		worker.signals.finished.connect(lambda: self.on_task_finished(worker, on_success, on_failure or self.show_error))
		self.thread_pool.start(worker)
		return True

	def on_task_finished(self, worker : Worker, on_success : Optional[Callable[[Any], None]], on_failure : Callable[[str], None]) -> None:
		self.workers.discard(worker)
		self.set_busy(False)

		if worker.error is not None:
			on_failure(worker.error)
		elif on_success:
			on_success(worker.result)

	def set_busy(self, busy : bool, text : str = '', cancellable : bool = False) -> None:
		self.busy = busy
		self.cancel_button.setEnabled(busy and cancellable)
		if busy:
			self.status_label.setText(text)
			self.progress_bar.setRange(0, 0)
		else:
			self.progress_bar.setRange(0, 100)
			self.progress_bar.setValue(0)
			self.progress_bar.setFormat('%p%')
		self.busy_changed.emit(busy)

	def update_progress(self, description : str, current : int, total : int) -> None:
		if self.busy and total > 0:
			self.progress_bar.setRange(0, total)
			self.progress_bar.setValue(min(current, total))
			self.progress_bar.setFormat(description.capitalize() + ' %v / %m')

	def cancel(self) -> None:
		self.status_label.setText('Cancelling...')
		self.cancel_requested.emit()
		engine.cancel()

	def show_error(self, message : str) -> None:
		self.status_label.setText(message)
		QMessageBox.warning(self, 'FaceSwap', message)

	def open_output_folder(self) -> None:
		os.makedirs(self.settings.output_path, exist_ok = True)
		QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings.output_path))

	def open_settings(self) -> None:
		from app.ui.settings_dialog import SettingsDialog

		dialog = SettingsDialog(self.settings, self)
		previous_models_path = self.settings.get_models_path()
		previous_execution = (self.settings.execution_device, self.settings.low_vram)

		if dialog.exec():
			dialog.apply_to(self.settings)
			save_settings(self.settings)

			if self.settings.get_models_path() != previous_models_path:
				QMessageBox.information(self, 'FaceSwap', 'The new models folder is used after restarting the app.')
			if (self.settings.execution_device, self.settings.low_vram) != previous_execution and self.engine_ready:
				self.run_task(engine.configure_execution, (self.settings.execution_device, self.settings.low_vram), self.update_device_label, busy_text = 'Switching device...')

	def closeEvent(self, event : QCloseEvent) -> None:
		if self.busy:
			answer = QMessageBox.question(self, 'FaceSwap', 'A task is still running. Cancel it and quit?')
			if answer != QMessageBox.StandardButton.Yes:
				event.ignore()
				return
			engine.cancel()
			self.thread_pool.waitForDone(10000)
		event.accept()
