import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Optional

APP_NAME = 'FaceSwap'
PREFERRED_MODELS_PATH = os.path.join('E:' + os.sep, 'FaceSwap', 'models')


def get_config_directory() -> str:
	if os.name == 'nt':
		return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP_NAME)
	return os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), APP_NAME)


def get_data_directory() -> str:
	if os.name == 'nt':
		return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), APP_NAME)
	return os.path.join(os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')), APP_NAME)


def get_settings_path() -> str:
	return os.path.join(get_config_directory(), 'settings.json')


def get_fallback_models_path() -> str:
	return os.path.join(get_data_directory(), 'models')


def get_default_models_path() -> str:
	if os.name == 'nt':
		return PREFERRED_MODELS_PATH
	return get_fallback_models_path()


def get_default_output_path() -> str:
	return os.path.join(os.path.expanduser('~'), 'Videos', APP_NAME)


def is_drive_available(path : str) -> bool:
	drive, _ = os.path.splitdrive(os.path.abspath(path))
	return not drive or os.path.isdir(drive + os.sep)


def resolve_models_path(models_path : Optional[str]) -> str:
	if models_path and is_drive_available(models_path):
		return os.path.abspath(models_path)
	return get_fallback_models_path()


@dataclass
class Settings:
	models_path : str = ''
	output_path : str = ''
	execution_device : str = 'auto'
	face_swapper_model : str = 'inswapper_128'
	face_enhancer_enabled : bool = True
	face_enhancer_model : str = 'gfpgan_1.4'
	occlusion_mask_enabled : bool = True
	low_vram : bool = True

	def __post_init__(self) -> None:
		if not self.models_path:
			self.models_path = get_default_models_path()
		if not self.output_path:
			self.output_path = get_default_output_path()

	def get_models_path(self) -> str:
		return resolve_models_path(self.models_path)


def load_settings() -> Settings:
	settings_path = get_settings_path()
	known_keys = { field.name for field in fields(Settings) }

	if os.path.isfile(settings_path):
		try:
			with open(settings_path, 'r', encoding = 'utf-8') as settings_file:
				data = json.load(settings_file)
			return Settings(**{ key: value for key, value in data.items() if key in known_keys })
		except (OSError, ValueError, TypeError):
			pass
	return Settings()


def save_settings(settings : Settings) -> bool:
	settings_path = get_settings_path()

	try:
		os.makedirs(os.path.dirname(settings_path), exist_ok = True)
		with open(settings_path, 'w', encoding = 'utf-8') as settings_file:
			json.dump(asdict(settings), settings_file, indent = 4)
		return True
	except OSError:
		return False
