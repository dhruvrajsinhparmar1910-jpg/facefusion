# FaceSwap desktop app

PySide6 desktop front end for the FaceFusion engine in `facefusion/`.

## Features

- Tabs: Image, GIF, Video, Batch
- Shared source face and options panel: swapper model (InSwapper 128, HyperSwap, SimSwap 512), face enhancer (on by default), occlusion mask (on by default)
- Face picker: replace all faces or one chosen face (videos and GIFs use the selected frame as the reference)
- Before/after preview, progress bar and cancel
- Settings (File > Settings): models folder, output folder, device (Auto / CUDA / CPU), low VRAM mode

Models download on first use into `E:\FaceSwap\models`. When drive `E:` does not exist the app uses `%LOCALAPPDATA%\FaceSwap\models`. Settings live in `%APPDATA%\FaceSwap\settings.json`, logs of the packaged app in `%LOCALAPPDATA%\FaceSwap\logs`.

FaceFusion's content analyser stays active: flagged targets are blurred in the preview and refused when processing.

## GPU

On Windows the app uses `onnxruntime-gpu` with CUDA 12 and cuDNN 9 and falls back to CPU when CUDA is not usable. Low VRAM mode (default) keeps two execution threads and frees models after each job, which suits 4 GB cards such as the RTX 3050. InSwapper 128 FP16 is the lightest swapper.

## Run from source

```bash
pip install -r app/requirements.txt
```

On Windows add the CUDA runtime libraries:

```bash
pip install "onnxruntime-gpu[cuda,cudnn]==1.24.4"
```

`ffmpeg`, `ffprobe` and `curl` must be on `PATH`.

```bash
python -m app
```

## Build the exe

```bash
pip install pyinstaller==6.22.3
```

```bash
pyinstaller app/FaceSwap.spec --noconfirm
```

Set `FFMPEG_DIR` to a folder with `ffmpeg.exe` and `ffprobe.exe` to bundle them. The result is `dist/FaceSwap/FaceSwap.exe`; models are never bundled. `FaceSwap.exe --self-test report.txt` checks the build without opening a window.

GitHub Actions (`.github/workflows/build-windows.yml`) builds the exe on every push to `master` and uploads `dist/FaceSwap` as an artifact.
