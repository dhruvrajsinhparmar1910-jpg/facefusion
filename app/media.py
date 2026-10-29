import os
import shutil
import subprocess
from typing import List, Optional

IMAGE_EXTENSIONS = [ '.bmp', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.webp' ]
VIDEO_EXTENSIONS = [ '.avi', '.m4v', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.mxf', '.webm', '.wmv' ]
GIF_EXTENSIONS = [ '.gif' ]


def get_extension(file_path : str) -> str:
	return os.path.splitext(file_path)[1].lower()


def is_image_file(file_path : str) -> bool:
	return os.path.isfile(file_path) and get_extension(file_path) in IMAGE_EXTENSIONS


def is_video_file(file_path : str) -> bool:
	return os.path.isfile(file_path) and get_extension(file_path) in VIDEO_EXTENSIONS


def is_gif_file(file_path : str) -> bool:
	return os.path.isfile(file_path) and get_extension(file_path) in GIF_EXTENSIONS


def resolve_ffmpeg() -> Optional[str]:
	return shutil.which('ffmpeg')


def run_ffmpeg(arguments : List[str]) -> bool:
	ffmpeg_path = resolve_ffmpeg()

	if ffmpeg_path:
		commands = [ ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y' ] + arguments
		process = subprocess.run(commands, stdin = subprocess.DEVNULL, stdout = subprocess.DEVNULL, stderr = subprocess.PIPE)
		return process.returncode == 0
	return False


def convert_gif_to_video(gif_path : str, video_path : str) -> bool:
	return run_ffmpeg(
	[
		'-i', gif_path,
		'-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
		'-c:v', 'libx264',
		'-crf', '10',
		'-preset', 'veryfast',
		'-pix_fmt', 'yuv420p',
		'-an',
		video_path
	])


def convert_video_to_gif(video_path : str, gif_path : str) -> bool:
	return run_ffmpeg(
	[
		'-i', video_path,
		'-filter_complex', 'split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle',
		'-loop', '0',
		gif_path
	])


def suggest_output_path(output_directory : str, target_path : str, extension : Optional[str] = None) -> str:
	target_name, target_extension = os.path.splitext(os.path.basename(target_path))
	output_extension = extension or target_extension
	output_path = os.path.join(output_directory, target_name + '_swapped' + output_extension)
	index = 1

	while os.path.exists(output_path):
		output_path = os.path.join(output_directory, target_name + '_swapped_' + str(index) + output_extension)
		index += 1
	return output_path
