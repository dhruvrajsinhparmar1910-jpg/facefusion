# PyInstaller spec for the FaceSwap desktop app.
# Build from the repository root: pyinstaller app/FaceSwap.spec --noconfirm
# Models are never bundled; they download on first run into the configured models folder.
# Set FFMPEG_DIR to a folder holding ffmpeg and ffprobe to bundle them.

import glob
import os
import site
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT_PATH = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, ROOT_PATH)
FFMPEG_DIR = os.environ.get('FFMPEG_DIR', '')


def collect_nvidia_libraries():
	binaries = []
	library_pattern = '*.dll' if sys.platform == 'win32' else '*.so*'

	for site_path in site.getsitepackages():
		for library_path in glob.glob(os.path.join(site_path, 'nvidia', '*', 'bin' if sys.platform == 'win32' else 'lib', library_pattern)):
			binaries.append((library_path, os.path.join('onnxruntime', 'capi')))
	return binaries


def collect_ffmpeg():
	binaries = []

	if FFMPEG_DIR:
		for name in [ 'ffmpeg', 'ffprobe' ]:
			binary_path = os.path.join(FFMPEG_DIR, name + ('.exe' if sys.platform == 'win32' else ''))
			if not os.path.isfile(binary_path):
				raise SystemExit('Missing ' + binary_path)
			binaries.append((binary_path, 'ffmpeg'))
	return binaries


hidden_imports = collect_submodules('facefusion', filter = lambda name: not name.startswith('facefusion.uis')) + collect_submodules('app')

if 'facefusion.processors.modules.face_swapper.core' not in hidden_imports:
	raise SystemExit('Could not collect the facefusion modules')

analysis = Analysis(
	[ os.path.join(ROOT_PATH, 'app', '__main__.py') ],
	pathex = [ ROOT_PATH ],
	binaries = collect_dynamic_libs('onnxruntime') + collect_nvidia_libraries() + collect_ffmpeg(),
	datas = [ (os.path.join(ROOT_PATH, 'facefusion.ico'), '.') ],
	hiddenimports = hidden_imports,
	excludes = [ 'facefusion.uis', 'gradio', 'gradio_rangeslider', 'tkinter', 'matplotlib', 'IPython' ],
	# keep facefusion as plain source: processors are discovered on disk and the content analyser checks its own source hash
	module_collection_mode = { 'facefusion': 'py' },
	noarchive = False
)
pyz = PYZ(analysis.pure)
exe = EXE(
	pyz,
	analysis.scripts,
	[],
	exclude_binaries = True,
	name = 'FaceSwap',
	icon = os.path.join(ROOT_PATH, 'facefusion.ico'),
	console = False,
	upx = False
)
collect = COLLECT(
	exe,
	analysis.binaries,
	analysis.datas,
	name = 'FaceSwap',
	upx = False
)
