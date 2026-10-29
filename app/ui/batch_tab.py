import os
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app import engine, media

if TYPE_CHECKING:
	from app.ui.main_window import MainWindow

BATCH_FILTER = 'Media (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif *.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.mpeg *.mpg)'
BATCH_EXTENSIONS = media.IMAGE_EXTENSIONS + media.GIF_EXTENSIONS + media.VIDEO_EXTENSIONS


class BatchSignals(QObject):
	item_changed = Signal(int, str)


class BatchTab(QWidget):
	def __init__(self, main_window : 'MainWindow') -> None:
		super().__init__()
		self.main_window = main_window
		self.cancelled = False
		self.signals = BatchSignals()
		self.signals.item_changed.connect(self.set_item_status)

		layout = QVBoxLayout(self)
		layout.addWidget(QLabel('Swap your source face into many images, GIFs and videos. Results go to the output folder.'))

		self.table = QTableWidget(0, 2)
		self.table.setHorizontalHeaderLabels([ 'Target', 'Status' ])
		self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
		self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
		self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
		self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
		layout.addWidget(self.table, 1)

		buttons_layout = QHBoxLayout()
		self.add_files_button = QPushButton('Add files...')
		self.add_files_button.clicked.connect(self.add_files)
		self.add_folder_button = QPushButton('Add folder...')
		self.add_folder_button.clicked.connect(self.add_folder)
		self.remove_button = QPushButton('Remove')
		self.remove_button.clicked.connect(self.remove_selected)
		self.clear_button = QPushButton('Clear')
		self.clear_button.clicked.connect(lambda: self.table.setRowCount(0))
		self.face_mode_combo = QComboBox()
		self.face_mode_combo.addItem('All faces', 'all')
		self.face_mode_combo.addItem('Largest face only', 'largest')
		self.start_button = QPushButton('Start batch')
		self.start_button.setMinimumWidth(140)
		self.start_button.clicked.connect(self.start)
		for widget in [ self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button ]:
			buttons_layout.addWidget(widget)
		buttons_layout.addStretch(1)
		buttons_layout.addWidget(QLabel('Replace'))
		buttons_layout.addWidget(self.face_mode_combo)
		buttons_layout.addWidget(self.start_button)
		layout.addLayout(buttons_layout)

		self.main_window.busy_changed.connect(self.update_controls)
		self.main_window.ready_changed.connect(lambda _: self.update_controls())
		self.main_window.side_panel.changed.connect(self.update_controls)
		self.main_window.cancel_requested.connect(self.cancel)
		self.update_controls()

	def update_controls(self, busy : Optional[bool] = None) -> None:
		busy = self.main_window.busy if busy is None else busy
		for widget in [ self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button, self.face_mode_combo ]:
			widget.setEnabled(not busy)
		self.start_button.setEnabled(self.main_window.engine_ready and not busy and bool(self.main_window.side_panel.source_paths))

	def add_paths(self, paths : List[str]) -> None:
		existing_paths = { self.table.item(row, 0).text() for row in range(self.table.rowCount()) }

		for path in paths:
			if os.path.splitext(path)[1].lower() in BATCH_EXTENSIONS and path not in existing_paths:
				row = self.table.rowCount()
				self.table.insertRow(row)
				self.table.setItem(row, 0, QTableWidgetItem(path))
				self.table.setItem(row, 1, QTableWidgetItem('Queued'))
				existing_paths.add(path)

	def add_files(self) -> None:
		paths, _ = QFileDialog.getOpenFileNames(self, 'Add targets', '', BATCH_FILTER)
		self.add_paths(paths)

	def add_folder(self) -> None:
		directory = QFileDialog.getExistingDirectory(self, 'Add folder')
		if directory:
			self.add_paths(sorted(os.path.join(directory, name) for name in os.listdir(directory)))

	def remove_selected(self) -> None:
		for row in sorted({ index.row() for index in self.table.selectedIndexes() }, reverse = True):
			self.table.removeRow(row)

	def set_item_status(self, row : int, status : str) -> None:
		if row < self.table.rowCount():
			self.table.setItem(row, 1, QTableWidgetItem(status))

	def cancel(self) -> None:
		self.cancelled = True

	def start(self) -> None:
		target_paths = [ self.table.item(row, 0).text() for row in range(self.table.rowCount()) ]
		if not target_paths:
			return
		for row in range(len(target_paths)):
			self.set_item_status(row, 'Queued')
		self.cancelled = False
		self.main_window.run_task(self.process_batch, (target_paths, self.face_mode_combo.currentData()), self.on_batch_finished, busy_text = 'Batch running...', cancellable = True)

	def process_batch(self, target_paths : List[str], face_mode : str) -> str:
		succeeded = 0

		for row, target_path in enumerate(target_paths):
			if self.cancelled:
				self.signals.item_changed.emit(row, 'Cancelled')
				continue
			self.signals.item_changed.emit(row, 'Processing...')
			output_path = media.suggest_output_path(self.main_window.settings.output_path, target_path)
			options = self.main_window.side_panel.create_options(target_path, output_path)
			options.face_mode = face_mode

			try:
				result = engine.run(options)
				self.signals.item_changed.emit(row, 'Done' if result.success else result.message)
				succeeded += int(result.success)
			except Exception as exception:
				self.signals.item_changed.emit(row, 'Error: ' + str(exception))

		return str(succeeded) + ' of ' + str(len(target_paths)) + ' finished'

	def on_batch_finished(self, message : str) -> None:
		self.main_window.status_label.setText('Batch: ' + message)
