import sys, json, os, ctypes, subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

wav_path = sys.argv[1]
model_size = sys.argv[2]
model_dir = sys.argv[3] if len(sys.argv) > 3 else None

os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
from faster_whisper import WhisperModel

cuda_version = None
try:
    ctypes.CDLL("cublas64_12.dll")
    cuda_version = "12.x"
except OSError:
    try:
        ctypes.CDLL("cublas64_11.dll")
        cuda_version = "11.x"
    except OSError:
        pass

model = None
if cuda_version:
    sys.stderr.write(f"  演算ユニット: CUDA {cuda_version}\n")
    compute_types = ["int8"]
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            creationflags=subprocess.CREATE_NO_WINDOW
        ).decode().strip()
        cc = float(out.split("\n")[0])
        if cc >= 7.0:
            compute_types = ["int8_float16", "float16", "int8"]
    except Exception:
        pass
    sys.stderr.write(f"  compute_type 試行順: {compute_types}\n")
    for ct in compute_types:
        try:
            sys.stderr.write(f"  compute_type = {ct} を試行...\n")
            model = WhisperModel(model_size, device="cuda", compute_type=ct, download_root=model_dir)
            segments, info = model.transcribe(wav_path, language="ja", beam_size=1, vad_filter=True)
            sys.stderr.write(f"  検出言語: {info.language} (確度: {info.language_probability:.2f})\n")
            break
        except Exception as e:
            sys.stderr.write(f"  {ct} 非対応 ({e}) → {'float16' if ct == 'int8_float16' else 'int8'} へフォールバック\n")

if model is None:
    sys.stderr.write("  演算ユニット: CPU\n")
    model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=model_dir)
    segments, info = model.transcribe(wav_path, language="ja", beam_size=1, vad_filter=True)
    sys.stderr.write(f"  検出言語: {info.language} (確度: {info.language_probability:.2f})\n")

result = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
print(json.dumps(result, ensure_ascii=False))
