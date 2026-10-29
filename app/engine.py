import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy

from app import media
from app.settings import Settings, get_data_directory

ERROR_MESSAGES =\
{
	1: 'Processing failed.',
	2: 'Could not start processing. Check the source face and target file.',
	3: 'The content filter blocked this target.',
	4: 'Processing was cancelled.'
}
FACE_SWAPPER_MODELS =\
[
	('inswapper_128', 'InSwapper 128'),
	('inswapper_128_fp16', 'InSwapper 128 (FP16, low VRAM)'),
	('hyperswap_1a_256', 'HyperSwap 1A 256'),
	('hyperswap_1b_256', 'HyperSwap 1B 256'),
	('hyperswap_1c_256', 'HyperSwap 1C 256'),
	('simswap_unofficial_512', 'SimSwap 512')
]
FACE_ENHANCER_MODELS =\
[
	('gfpgan_1.4', 'GFPGAN 1.4'),
	('codeformer', 'CodeFormer'),
	('gpen_bfr_512', 'GPEN BFR 512'),
	('restoreformer_plus_plus', 'RestoreFormer++')
]
ENGINE_LOCK = threading.Lock()
GIF_VIDEO_CACHE : Dict[str, str] = {}
ACTIVE_DEVICE : str = 'cpu'


@dataclass
class SwapOptions:
	source_paths : List[str]
	target_path : str
	output_path : str = ''
	face_swapper_model : str = 'inswapper_128'
	face_enhancer_enabled : bool = True
	face_enhancer_model : str = 'gfpgan_1.4'
	occlusion_mask_enabled : bool = True
	face_position : Optional[int] = None
	reference_frame_number : int = 0


@dataclass
class RunResult:
	success : bool
	output_path : str
	message : str


class ErrorCollector(logging.Handler):
	def __init__(self) -> None:
		super().__init__(logging.ERROR)
		self.messages : List[str] = []

	def emit(self, record : logging.LogRecord) -> None:
		self.messages.append(record.getMessage())

	def pop_last(self) -> Optional[str]:
		message = self.messages[-1] if self.messages else None
		self.messages.clear()
		return message


ERROR_COLLECTOR = ErrorCollector()


def get_work_directory() -> str:
	work_directory = os.path.join(tempfile.gettempdir(), 'FaceSwap')
	os.makedirs(work_directory, exist_ok = True)
	return work_directory


def bootstrap(settings : Settings) -> None:
	models_path = settings.get_models_path()
	os.makedirs(models_path, exist_ok = True)
	os.environ['FACEFUSION_MODELS_PATH'] = models_path

	from facefusion import logger, state_manager
	from facefusion.args import apply_args
	from facefusion.program import create_program

	jobs_path = os.path.join(get_data_directory(), 'jobs')
	program = create_program()
	args = vars(program.parse_args([ 'headless-run', '--jobs-path', jobs_path, '--processors', 'face_swapper', 'face_enhancer', '--log-level', 'info' ]))
	apply_args(args, state_manager.init_item)
	logger.init('info')
	logger.get_package_logger().addHandler(ERROR_COLLECTOR)

	state_manager.set_item('face_detector_size', '640x640')
	state_manager.set_item('output_image_quality', 95)
	state_manager.set_item('output_video_quality', 90)
	state_manager.set_item('output_video_preset', 'fast')
	state_manager.set_item('face_enhancer_blend', 80)
	configure_execution(settings.execution_device, settings.low_vram)


def probe_cuda() -> bool:
	import onnxruntime
	from onnx import TensorProto, helper

	if 'CUDAExecutionProvider' not in onnxruntime.get_available_providers():
		return False

	if hasattr(onnxruntime, 'preload_dlls'):
		try:
			onnxruntime.preload_dlls()
		except Exception:
			pass

	graph = helper.make_graph([ helper.make_node('Identity', [ 'input' ], [ 'output' ]) ], 'probe',
		[ helper.make_tensor_value_info('input', TensorProto.FLOAT, [ 1 ]) ],
		[ helper.make_tensor_value_info('output', TensorProto.FLOAT, [ 1 ]) ])
	model = helper.make_model(graph, opset_imports = [ helper.make_opsetid('', 13) ])
	model.ir_version = 8

	try:
		session = onnxruntime.InferenceSession(model.SerializeToString(), providers = [ 'CUDAExecutionProvider', 'CPUExecutionProvider' ])
		return session.get_providers()[0] == 'CUDAExecutionProvider'
	except Exception:
		return False


def configure_execution(execution_device : str, low_vram : bool) -> str:
	global ACTIVE_DEVICE

	from facefusion import inference_manager, state_manager

	use_cuda = execution_device in [ 'auto', 'cuda' ] and probe_cuda()

	if use_cuda:
		state_manager.set_item('execution_providers', [ 'cuda', 'cpu' ])
		state_manager.set_item('execution_thread_count', 2 if low_vram else 4)
		ACTIVE_DEVICE = 'cuda'
	else:
		state_manager.set_item('execution_providers', [ 'cpu' ])
		state_manager.set_item('execution_thread_count', min(8, max(1, (os.cpu_count() or 2) // 2)))
		ACTIVE_DEVICE = 'cpu'

	state_manager.set_item('execution_device_ids', [ 0 ])
	state_manager.set_item('video_memory_strategy', 'strict' if low_vram else 'moderate')
	inference_manager.resolve_static_inference_providers.cache_clear()
	for app_context in inference_manager.INFERENCE_POOL_SET:
		inference_manager.INFERENCE_POOL_SET[app_context].clear()
	return ACTIVE_DEVICE


def get_active_device() -> str:
	return ACTIVE_DEVICE


def check_dependencies() -> List[str]:
	import shutil

	return [ dependency for dependency in [ 'curl', 'ffmpeg', 'ffprobe' ] if not shutil.which(dependency) ]


def resolve_target_path(target_path : str) -> str:
	if media.is_gif_file(target_path):
		cache_key = os.path.abspath(target_path) + ':' + str(os.path.getmtime(target_path))
		video_path = GIF_VIDEO_CACHE.get(cache_key)

		if not video_path or not os.path.isfile(video_path):
			gif_directory = tempfile.mkdtemp(prefix = 'gif_', dir = get_work_directory())
			video_path = os.path.join(gif_directory, os.path.splitext(os.path.basename(target_path))[0] + '.mp4')

			if not media.convert_gif_to_video(target_path, video_path):
				raise RuntimeError('Could not convert GIF: ' + target_path)
			GIF_VIDEO_CACHE[cache_key] = video_path
		return video_path
	return target_path


def apply_options(options : SwapOptions) -> None:
	from facefusion import state_manager
	from facefusion.processors.modules.face_swapper import choices as face_swapper_choices

	processors = [ 'face_swapper' ]
	if options.face_enhancer_enabled:
		processors.append('face_enhancer')

	state_manager.set_item('processors', processors)
	state_manager.set_item('source_paths', options.source_paths)
	state_manager.set_item('face_swapper_model', options.face_swapper_model)
	state_manager.set_item('face_swapper_pixel_boost', face_swapper_choices.face_swapper_set.get(options.face_swapper_model)[0])
	state_manager.set_item('face_enhancer_model', options.face_enhancer_model)
	state_manager.set_item('face_mask_types', [ 'box', 'occlusion' ] if options.occlusion_mask_enabled else [ 'box' ])
	state_manager.set_item('reference_frame_number', options.reference_frame_number)
	state_manager.set_item('workflow_mode', 'auto')

	if options.face_position is None:
		state_manager.set_item('face_selector_mode', 'many')
	else:
		state_manager.set_item('face_selector_mode', 'reference')
		state_manager.set_item('reference_face_position', options.face_position)


def apply_target_path(target_path : str) -> None:
	from facefusion import state_manager
	from facefusion.vision import detect_video_fps

	state_manager.set_item('target_path', target_path)
	state_manager.set_item('output_video_fps', None if media.is_image_file(target_path) else detect_video_fps(target_path))


def ensure_models() -> bool:
	from facefusion import core

	return core.common_pre_check() and core.processors_pre_check()


def pop_error_message(error_code : int = 1) -> str:
	return ERROR_COLLECTOR.pop_last() or ERROR_MESSAGES.get(error_code, ERROR_MESSAGES.get(1))


def read_target_frame(target_path : str, frame_number : int = 0) -> Optional[numpy.ndarray]:
	from facefusion.vision import read_static_image, read_video_frame

	resolved_path = resolve_target_path(target_path)

	if media.is_image_file(resolved_path):
		return read_static_image(resolved_path)
	return read_video_frame(resolved_path, frame_number)


def count_target_frames(target_path : str) -> int:
	from facefusion.vision import count_video_frame_total

	resolved_path = resolve_target_path(target_path)

	if media.is_image_file(resolved_path):
		return 1
	return count_video_frame_total(resolved_path)


def detect_target_faces(source_paths : List[str], target_path : str, frame_number : int = 0) -> List[numpy.ndarray]:
	from facefusion.face_creator import get_static_faces
	from facefusion.face_selector import sort_and_filter_faces
	from facefusion.vision import fit_cover_frame, read_static_images

	with ENGINE_LOCK:
		if not ensure_models():
			raise RuntimeError(pop_error_message())

		target_vision_frame = read_target_frame(target_path, frame_number)
		if target_vision_frame is None:
			return []

		source_faces = get_static_faces(read_static_images(source_paths))
		target_faces = sort_and_filter_faces(source_faces, get_static_faces([ target_vision_frame ]))
		thumbnails = []

		for target_face in target_faces:
			crop_vision_frame = extract_face_crop(target_vision_frame, target_face.bounding_box)
			crop_vision_frame = fit_cover_frame(crop_vision_frame, (128, 128))
			thumbnails.append(cv2.cvtColor(crop_vision_frame, cv2.COLOR_BGR2RGB))
		return thumbnails


def extract_face_crop(vision_frame : numpy.ndarray, bounding_box : numpy.ndarray) -> numpy.ndarray:
	start_x, start_y, end_x, end_y = map(int, bounding_box)
	padding_x = int((end_x - start_x) * 0.25)
	padding_y = int((end_y - start_y) * 0.25)
	start_x = max(0, start_x - padding_x)
	start_y = max(0, start_y - padding_y)
	end_x = max(0, end_x + padding_x)
	end_y = max(0, end_y + padding_y)
	return vision_frame[start_y:end_y, start_x:end_x]


def preview(options : SwapOptions, frame_number : int = 0, max_size : int = 1024) -> Tuple[numpy.ndarray, numpy.ndarray]:
	from facefusion import logger, state_manager
	from facefusion.audio import create_empty_audio_frame
	from facefusion.content_analyser import analyse_frame
	from facefusion.processors.core import get_processors_modules
	from facefusion.vision import extract_vision_mask, obscure_frame, read_static_image, read_static_images, read_video_frame, restrict_frame, select_video_frames

	with ENGINE_LOCK:
		target_path = resolve_target_path(options.target_path)
		apply_options(options)
		apply_target_path(target_path)
		state_manager.set_item('workflow_mode', 'image-to-image' if media.is_image_file(target_path) else 'image-to-video')

		if not ensure_models():
			raise RuntimeError(pop_error_message())

		if media.is_image_file(target_path):
			reference_vision_frame = read_static_image(target_path)
			target_vision_frames = [ reference_vision_frame ]
		else:
			reference_vision_frame = read_video_frame(target_path, options.reference_frame_number)
			target_vision_frames = select_video_frames(target_path, frame_number, state_manager.get_item('target_frame_amount'))

		if reference_vision_frame is None or not target_vision_frames:
			raise RuntimeError('Could not read the target file.')

		target_vision_frames = [ restrict_frame(vision_frame, (max_size, max_size))[:, :, :3] for vision_frame in target_vision_frames ]
		target_vision_frame = target_vision_frames[len(target_vision_frames) // 2]
		temp_vision_frame = target_vision_frame.copy()

		if analyse_frame(target_vision_frame):
			obscured_vision_frame = obscure_frame(target_vision_frame)
			return to_rgb(obscured_vision_frame), to_rgb(obscured_vision_frame)

		temp_vision_mask = extract_vision_mask(temp_vision_frame)
		source_vision_frames = read_static_images(options.source_paths)

		for processor_module in get_processors_modules(state_manager.get_item('processors')):
			logger.disable()
			if processor_module.pre_process('preview'):
				logger.enable()
				temp_vision_frame, temp_vision_mask = processor_module.process_frame(
				{
					'reference_vision_frame': reference_vision_frame,
					'source_audio_frame': create_empty_audio_frame(),
					'source_voice_frame': create_empty_audio_frame(),
					'source_vision_frames': source_vision_frames,
					'target_vision_frames': target_vision_frames,
					'temp_vision_frame': temp_vision_frame[:, :, :3],
					'temp_vision_mask': temp_vision_mask
				})
			logger.enable()

		return to_rgb(target_vision_frame), to_rgb(temp_vision_frame[:, :, :3])


def to_rgb(vision_frame : numpy.ndarray) -> numpy.ndarray:
	return numpy.ascontiguousarray(cv2.cvtColor(vision_frame[:, :, :3], cv2.COLOR_BGR2RGB))


def run(options : SwapOptions) -> RunResult:
	from facefusion import core, state_manager
	from facefusion.temp_helper import clear_temp_directory

	with ENGINE_LOCK:
		is_gif = media.is_gif_file(options.target_path)
		target_path = resolve_target_path(options.target_path)
		output_path = options.output_path
		work_output_path = output_path

		os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok = True)
		if is_gif:
			work_output_path = os.path.join(os.path.dirname(target_path), os.path.splitext(os.path.basename(target_path))[0] + '_output.mp4')

		apply_options(options)
		apply_target_path(target_path)
		state_manager.set_item('output_path', work_output_path)
		state_manager.set_item('output_audio_volume', 0 if is_gif else 100)
		ERROR_COLLECTOR.pop_last()

		try:
			if not ensure_models():
				return RunResult(False, output_path, pop_error_message())

			error_code = core.conditional_process()
		except SystemExit as exception:
			error_code = exception.code if isinstance(exception.code, int) and exception.code else 1
		finally:
			clear_temp_directory(target_path)

		if error_code:
			return RunResult(False, output_path, ERROR_MESSAGES.get(error_code) if error_code in [ 3, 4 ] else pop_error_message(error_code))

		if is_gif:
			converted = media.convert_video_to_gif(work_output_path, output_path)
			if os.path.isfile(work_output_path):
				os.remove(work_output_path)
			if not converted:
				return RunResult(False, output_path, 'Could not write the GIF output.')

		return RunResult(True, output_path, 'Saved to ' + output_path)


def cancel() -> None:
	from facefusion import process_manager

	if process_manager.is_processing():
		process_manager.stop()
