import os
from typing import Any, List, Optional, TYPE_CHECKING, Tuple

import numpy
from PySide6.QtCore import QSize, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget

from app import engine, media
from app.ui.widgets import ImageView, TitledView, numpy_to_pixmap

if TYPE_CHECKING:
	from app.ui.main_window import MainWindow

TAB_KINDS =\
{
	'image': ('Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)', media.IMAGE_EXTENSIONS),
	'gif': ('GIF (*.gif)', media.GIF_EXTENSIONS),
	'video': ('Videos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.mpeg *.mpg)', media.VIDEO_EXTENSIONS)
}


class SwapTab(QWidget):
	def __init__(self, main_window : 'MainWindow', kind : str) -> None:
		super().__init__()
		self.main_window = main_window
		self.kind = kind
		self.file_filter, self.extensions = TAB_KINDS.get(kind)
		self.target_path = ''
		self.output_path = ''
		self.reference_frame_number = 0

		layout = QVBoxLayout(self)

		target_layout = QHBoxLayout()
		self.target_label = QLabel('No target selected. Drop a file on the preview or choose one.')
		self.target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
		target_button = QPushButton('Choose target...')
		target_button.clicked.connect(self.browse_target)
		target_layout.addWidget(self.target_label, 1)
		target_layout.addWidget(target_button)
		layout.addLayout(target_layout)

		self.frame_slider = QSlider(Qt.Orientation.Horizontal)
		self.frame_spin = QSpinBox()
		self.frame_slider.valueChanged.connect(self.frame_spin.setValue)
		self.frame_spin.valueChanged.connect(self.frame_slider.setValue)
		self.frame_slider.sliderReleased.connect(self.on_frame_selected)
		self.frame_spin.editingFinished.connect(self.on_frame_selected)
		self.frame_widget = QWidget()
		frame_layout = QHBoxLayout(self.frame_widget)
		frame_layout.setContentsMargins(0, 0, 0, 0)
		frame_layout.addWidget(QLabel('Frame'))
		frame_layout.addWidget(self.frame_slider, 1)
		frame_layout.addWidget(self.frame_spin)
		self.frame_widget.setVisible(kind != 'image')
		layout.addWidget(self.frame_widget)

		faces_label = QLabel('Faces to replace (pick one, or keep "All faces")')
		self.faces_list = QListWidget()
		self.faces_list.setViewMode(QListView.ViewMode.IconMode)
		self.faces_list.setFlow(QListView.Flow.LeftToRight)
		self.faces_list.setWrapping(False)
		self.faces_list.setIconSize(QSize(88, 88))
		self.faces_list.setFixedHeight(130)
		self.faces_list.setMovement(QListView.Movement.Static)
		self.faces_list.currentRowChanged.connect(lambda _: self.request_preview())
		layout.addWidget(faces_label)
		layout.addWidget(self.faces_list)

		previews_layout = QHBoxLayout()
		self.before_view = ImageView('Drop a target file here', self.extensions)
		self.before_view.files_dropped.connect(lambda paths: self.set_target_path(paths[0]))
		self.after_view = ImageView('Preview appears here')
		previews_layout.addWidget(TitledView('Before', self.before_view), 1)
		previews_layout.addWidget(TitledView('After', self.after_view), 1)
		layout.addLayout(previews_layout, 1)

		buttons_layout = QHBoxLayout()
		self.preview_button = QPushButton('Update preview')
		self.preview_button.clicked.connect(self.request_preview)
		self.start_button = QPushButton('Start')
		self.start_button.setDefault(True)
		self.start_button.setMinimumWidth(140)
		self.start_button.clicked.connect(self.start)
		self.open_output_button = QPushButton('Open result')
		self.open_output_button.setEnabled(False)
		self.open_output_button.clicked.connect(self.open_output)
		buttons_layout.addWidget(self.preview_button)
		buttons_layout.addStretch(1)
		buttons_layout.addWidget(self.open_output_button)
		buttons_layout.addWidget(self.start_button)
		layout.addLayout(buttons_layout)

		self.main_window.busy_changed.connect(self.update_controls)
		self.main_window.ready_changed.connect(lambda _: self.update_controls())
		self.main_window.side_panel.changed.connect(self.on_source_changed)
		self.update_controls()

	def update_controls(self, busy : Optional[bool] = None) -> None:
		busy = self.main_window.busy if busy is None else busy
		has_inputs = bool(self.target_path and self.main_window.side_panel.source_paths)
		enabled = self.main_window.engine_ready and not busy
		self.preview_button.setEnabled(enabled and has_inputs)
		self.start_button.setEnabled(enabled and has_inputs)
		self.frame_slider.setEnabled(enabled and bool(self.target_path))
		self.frame_spin.setEnabled(enabled and bool(self.target_path))

	def browse_target(self) -> None:
		path, _ = QFileDialog.getOpenFileName(self, 'Choose target', '', self.file_filter)
		if path:
			self.set_target_path(path)

	def set_target_path(self, path : str) -> None:
		if os.path.splitext(path)[1].lower() not in self.extensions:
			return
		self.target_path = path
		self.target_label.setText(path)
		self.faces_list.clear()
		self.after_view.clear_image()
		self.open_output_button.setEnabled(False)
		self.reference_frame_number = 0
		self.update_controls()
		self.main_window.run_task(self.load_target, (path,), self.on_target_loaded, busy_text = 'Loading target...')

	def load_target(self, path : str) -> Tuple[int, Optional[numpy.ndarray], List[numpy.ndarray]]:
		frame_total = engine.count_target_frames(path)
		frame = engine.read_target_frame(path, 0)
		faces = engine.detect_target_faces(self.main_window.side_panel.source_paths, path, 0)
		return frame_total, frame, faces

	def on_target_loaded(self, result : Tuple[int, Optional[numpy.ndarray], List[numpy.ndarray]]) -> None:
		frame_total, frame, faces = result
		self.frame_slider.blockSignals(True)
		self.frame_slider.setRange(0, max(0, frame_total - 1))
		self.frame_spin.setRange(0, max(0, frame_total - 1))
		self.frame_slider.setValue(0)
		self.frame_slider.blockSignals(False)
		self.show_frame(frame)
		self.populate_faces(faces)
		self.main_window.status_label.setText(str(len(faces)) + ' face(s) found')
		self.request_preview()

	def show_frame(self, frame : Optional[numpy.ndarray]) -> None:
		if frame is not None:
			self.before_view.set_array(numpy.ascontiguousarray(frame[:, :, 2::-1]))

	def on_frame_selected(self) -> None:
		if self.target_path:
			self.main_window.run_task(self.load_frame, (self.target_path, self.frame_slider.value()), self.on_frame_loaded, busy_text = 'Reading frame...')

	def load_frame(self, path : str, frame_number : int) -> Tuple[int, Optional[numpy.ndarray], List[numpy.ndarray]]:
		frame = engine.read_target_frame(path, frame_number)
		faces = engine.detect_target_faces(self.main_window.side_panel.source_paths, path, frame_number)
		return frame_number, frame, faces

	def on_frame_loaded(self, result : Tuple[int, Optional[numpy.ndarray], List[numpy.ndarray]]) -> None:
		frame_number, frame, faces = result
		self.reference_frame_number = frame_number
		self.show_frame(frame)
		self.populate_faces(faces)
		self.request_preview()

	def populate_faces(self, faces : List[numpy.ndarray]) -> None:
		self.faces_list.blockSignals(True)
		self.faces_list.clear()
		self.faces_list.addItem(QListWidgetItem('All faces'))
		for index, face in enumerate(faces):
			item = QListWidgetItem(QIcon(numpy_to_pixmap(face)), 'Face ' + str(index + 1))
			item.setData(Qt.ItemDataRole.UserRole, index)
			self.faces_list.addItem(item)
		self.faces_list.setCurrentRow(0)
		self.faces_list.blockSignals(False)

	def on_source_changed(self) -> None:
		self.update_controls()
		if self.target_path and self.main_window.engine_ready and self.isVisible():
			self.request_preview()

	def create_options(self, output_path : str = '') -> engine.SwapOptions:
		options = self.main_window.side_panel.create_options(self.target_path, output_path)
		item = self.faces_list.currentItem()
		face_position = item.data(Qt.ItemDataRole.UserRole) if item else None

		if face_position is not None:
			options.face_mode = 'reference'
			options.face_position = int(face_position)
		options.reference_frame_number = self.reference_frame_number
		return options

	def request_preview(self) -> None:
		if self.target_path and self.main_window.side_panel.source_paths:
			options = self.create_options()
			self.main_window.run_task(engine.preview, (options, self.frame_slider.value()), self.on_preview_ready, busy_text = 'Rendering preview...')

	def on_preview_ready(self, result : Tuple[Any, Any]) -> None:
		before, after = result
		self.before_view.set_array(before)
		self.after_view.set_array(after)
		self.main_window.status_label.setText('Preview ready')

	def start(self) -> None:
		extension = '.gif' if self.kind == 'gif' else None
		self.output_path = media.suggest_output_path(self.main_window.settings.output_path, self.target_path, extension)
		options = self.create_options(self.output_path)
		self.main_window.run_task(engine.run, (options,), self.on_run_finished, busy_text = 'Processing ' + os.path.basename(self.target_path) + '...', cancellable = True)

	def on_run_finished(self, result : engine.RunResult) -> None:
		self.main_window.status_label.setText(result.message)
		if result.success:
			self.open_output_button.setEnabled(True)
		elif result.message != engine.ERROR_MESSAGES.get(4):
			self.main_window.show_error(result.message)

	def open_output(self) -> None:
		if os.path.isfile(self.output_path):
			QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_path))
