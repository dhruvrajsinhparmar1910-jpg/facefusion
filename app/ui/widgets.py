import os
from typing import List, Optional

import numpy
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget


def numpy_to_pixmap(vision_frame : numpy.ndarray) -> QPixmap:
	vision_frame = numpy.ascontiguousarray(vision_frame)
	height, width = vision_frame.shape[:2]
	image = QImage(vision_frame.data, width, height, width * 3, QImage.Format.Format_RGB888)
	return QPixmap.fromImage(image.copy())


class ImageView(QLabel):
	files_dropped = Signal(list)

	def __init__(self, placeholder : str, extensions : Optional[List[str]] = None, minimum_size : QSize = QSize(240, 180)) -> None:
		super().__init__()
		self.placeholder = placeholder
		self.extensions = extensions
		self.source_pixmap : Optional[QPixmap] = None
		self.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.setMinimumSize(minimum_size)
		self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
		self.setFrameShape(QFrame.Shape.StyledPanel)
		self.setWordWrap(True)
		self.setAcceptDrops(extensions is not None)
		self.clear_image()

	def clear_image(self) -> None:
		self.source_pixmap = None
		self.setPixmap(QPixmap())
		self.setText(self.placeholder)

	def set_pixmap(self, pixmap : Optional[QPixmap]) -> None:
		if pixmap is None or pixmap.isNull():
			self.clear_image()
			return
		self.source_pixmap = pixmap
		self.update_scaled_pixmap()

	def set_array(self, vision_frame : Optional[numpy.ndarray]) -> None:
		self.set_pixmap(numpy_to_pixmap(vision_frame) if vision_frame is not None else None)

	def update_scaled_pixmap(self) -> None:
		if self.source_pixmap:
			self.setPixmap(self.source_pixmap.scaled(self.size() - QSize(4, 4), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

	def resizeEvent(self, event : QResizeEvent) -> None:
		super().resizeEvent(event)
		self.update_scaled_pixmap()

	def filter_paths(self, event : QDropEvent) -> List[str]:
		paths = [ url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile() ]
		return [ path for path in paths if os.path.splitext(path)[1].lower() in (self.extensions or []) ]

	def dragEnterEvent(self, event : QDragEnterEvent) -> None:
		if event.mimeData().hasUrls() and self.filter_paths(event):
			event.acceptProposedAction()

	def dropEvent(self, event : QDropEvent) -> None:
		paths = self.filter_paths(event)
		if paths:
			self.files_dropped.emit(paths)


class TitledView(QWidget):
	def __init__(self, title : str, view : QWidget) -> None:
		super().__init__()
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		title_label = QLabel(title)
		title_label.setStyleSheet('font-weight: bold;')
		layout.addWidget(title_label)
		layout.addWidget(view, 1)
