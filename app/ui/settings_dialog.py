from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.settings import Settings, get_fallback_models_path


class SettingsDialog(QDialog):
	def __init__(self, settings : Settings, parent : QWidget) -> None:
		super().__init__(parent)
		self.setWindowTitle('Settings')
		self.setMinimumWidth(560)

		self.models_edit = QLineEdit(settings.models_path)
		self.output_edit = QLineEdit(settings.output_path)
		self.device_combo = QComboBox()
		self.device_combo.addItem('Auto (GPU if available)', 'auto')
		self.device_combo.addItem('GPU (CUDA)', 'cuda')
		self.device_combo.addItem('CPU', 'cpu')
		self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(settings.execution_device)))
		self.low_vram_check = QCheckBox('Low VRAM mode (recommended for 4 GB GPUs)')
		self.low_vram_check.setChecked(settings.low_vram)

		form_layout = QFormLayout()
		form_layout.addRow('Models folder', self.create_path_row(self.models_edit))
		form_layout.addRow('', QLabel('Used: ' + settings.get_models_path() + '\nFalls back to ' + get_fallback_models_path() + ' when the drive is missing.'))
		form_layout.addRow('Output folder', self.create_path_row(self.output_edit))
		form_layout.addRow('Device', self.device_combo)
		form_layout.addRow('', self.low_vram_check)

		button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		button_box.accepted.connect(self.accept)
		button_box.rejected.connect(self.reject)

		layout = QVBoxLayout(self)
		layout.addLayout(form_layout)
		layout.addWidget(button_box)

	def create_path_row(self, line_edit : QLineEdit) -> QWidget:
		row = QWidget()
		row_layout = QHBoxLayout(row)
		row_layout.setContentsMargins(0, 0, 0, 0)
		browse_button = QPushButton('Browse...')
		browse_button.clicked.connect(lambda: self.browse_directory(line_edit))
		row_layout.addWidget(line_edit, 1)
		row_layout.addWidget(browse_button)
		return row

	def browse_directory(self, line_edit : QLineEdit) -> None:
		directory = QFileDialog.getExistingDirectory(self, 'Choose folder', line_edit.text())
		if directory:
			line_edit.setText(directory)

	def apply_to(self, settings : Settings) -> None:
		settings.models_path = self.models_edit.text().strip() or settings.models_path
		settings.output_path = self.output_edit.text().strip() or settings.output_path
		settings.execution_device = self.device_combo.currentData()
		settings.low_vram = self.low_vram_check.isChecked()
