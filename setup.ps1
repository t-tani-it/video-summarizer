param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Write-Success($msg) {
    Write-Host "  [$([char]0x2714)] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "  [$([char]0x26A0)] $msg" -ForegroundColor Yellow
}

function Write-Info($msg) {
    Write-Host "  [i] $msg" -ForegroundColor Gray
}

function Test-Command($cmd) {
    try {
        Get-Command $cmd -ErrorAction Stop > $null
        return $true
    } catch {
        return $false
    }
}

Write-Step "Video Summarizer - セットアップ"
Write-Info "環境を自動検出し、最適な構成をインストールします。"

# ------------------------------------------------------------
# 1. Python 確認
# ------------------------------------------------------------
Write-Step "Python 確認"
if (-not (Test-Command "python")) {
    Write-Warn "python が見つかりません。https://www.python.org から Python 3.8+ をインストールしてください。"
    exit 1
}
$pyVer = python --version 2>&1
Write-Success $pyVer

# ------------------------------------------------------------
# 2. ffmpeg 確認
# ------------------------------------------------------------
Write-Step "ffmpeg 確認"
if (Test-Command "ffmpeg") {
    $ffVer = ffmpeg -version 2>&1 | Select-String -Pattern "ffmpeg version" | ForEach-Object { $_.ToString().Split(" ")[2] }
    Write-Success "ffmpeg $ffVer"
} else {
    Write-Warn "ffmpeg が見つかりません。以下のコマンドでインストールしてください。"
    Write-Host "    winget install ffmpeg" -ForegroundColor Yellow
    Write-Host "    または https://ffmpeg.org からダウンロードして PATH を通す" -ForegroundColor Yellow
    exit 1
}

# ------------------------------------------------------------
# 3. GPU / CUDA 検出
# ------------------------------------------------------------
Write-Step "GPU / CUDA 検出"

$detection = python -c "
import ctypes, json, subprocess, sys

result = {
    'cuda12': False,
    'cuda11': False,
    'compute_cap': None,
    'has_nvidia': False
}

# CUDA DLL 確認
for dll, key in [('cublas64_12.dll', 'cuda12'), ('cublas64_11.dll', 'cuda11')]:
    try:
        ctypes.CDLL(dll)
        result[key] = True
    except:
        pass

# CUDA Toolkit PATH も確認
for path in [r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.2\bin\cublas64_11.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.3\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.5\bin\cublas64_12.dll',
             r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\cublas64_12.dll']:
    import os
    if os.path.exists(path):
        key = 'cuda12' if '12' in path else 'cuda11'
        result[key] = True
        # 見つかった DLL のディレクトリを PATH に追加（後続のインストールで使うため）
        dll_dir = os.path.dirname(path)
        if dll_dir not in os.environ.get('PATH', ''):
            new_path = dll_dir + ';' + os.environ.get('PATH', '')
            os.environ['PATH'] = new_path
            print(f'    PATH に追加: {dll_dir}')

# nvidia-smi で compute capability 取得
try:
    out = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=compute_cap,name', '--format=csv,noheader'],
        text=True, creationflags=subprocess.CREATE_NO_WINDOW
    )
    lines = out.strip().split(chr(10))
    if lines and lines[0]:
        parts = lines[0].split(', ')
        result['compute_cap'] = float(parts[0]) if len(parts) > 0 else None
        result['gpu_name'] = parts[1] if len(parts) > 1 else 'Unknown'
        result['has_nvidia'] = True
except:
    pass

print(json.dumps(result))
" 2>&1 | Select-Object -Last 1

$det = $detection | ConvertFrom-Json

$configLabel = "CPU"
$packages = @()

if ($det.has_nvidia) {
    Write-Success "GPU 検出: $($det.gpu_name) (Compute Capability: $($det.compute_cap))"
    if ($det.cuda12) {
        Write-Success "CUDA 12.x DLL 利用可能"
    }
    if ($det.cuda11) {
        Write-Success "CUDA 11.x DLL 利用可能"
    }

    if ($det.compute_cap -ge 7.0 -and $det.cuda12) {
        $configLabel = "CUDA 12.x"
        $packages += @("ctranslate2", "faster-whisper")
        Write-Success "構成決定: CUDA 12.x (最新 ctranslate2 + faster-whisper)"
    } elseif ($det.compute_cap -ge 6.0 -and $det.cuda11) {
        $configLabel = "CUDA 11.x"
        $packages += @("ctranslate2==3.24.0", "faster-whisper==0.10.1")
        Write-Success "構成決定: CUDA 11.x (ctranslate2 3.24.0 + faster-whisper 0.10.1)"
    } elseif ($det.compute_cap -ge 6.0) {
        Write-Warn "GPU を検出しましたが、CUDA Runtime (cublas64_*.dll) が見つかりません。"
        Write-Warn "CUDA Toolkit をインストールすると GPU 処理が高速化されます。"
        Write-Info "ダウンロード: https://developer.nvidia.com/cuda-downloads"
        $configLabel = "CPU（推奨: CUDA Toolkit をインストール）"
        $packages += @("faster-whisper")
    } else {
        Write-Warn "GPU の Compute Capability $($det.compute_cap) はサポート外です。CPU で動作します。"
        $configLabel = "CPU（GPU 非対応）"
        $packages += @("faster-whisper")
    }
} else {
    Write-Info "NVIDIA GPU を検出しませんでした。CPU で動作します。"
    $configLabel = "CPU"
    $packages += @("faster-whisper")
}

# 常に janome を追加
$packages += @("janome")

# ------------------------------------------------------------
# 4. pip パッケージインストール
# ------------------------------------------------------------
Write-Step "パッケージインストール"

$pipArgs = @()
if ($Force) {
    $pipArgs += "--force-reinstall"
}

foreach ($pkg in $packages) {
    Write-Info "インストール: pip install $pkg"
    $pipCmd = "pip install $pkg $($pipArgs -join ' ')"
    try {
        $output = Invoke-Expression $pipCmd 2>&1 | Select-String -NotMatch "WARNING: Ignoring invalid distribution"
        Write-Success "$pkg インストール完了"
    } catch {
        Write-Warn "$pkg インストールに失敗しました: $_"
        exit 1
    }
}

# ------------------------------------------------------------
# 5. インストール後確認
# ------------------------------------------------------------
Write-Step "インストール後確認"

try {
    $check = python -c "
from faster_whisper import WhisperModel
from janome.tokenizer import Tokenizer
print('faster-whisper: OK')
print('janome: OK')

import ctranslate2
import os
print(f'ctranslate2: {ctranslate2.__version__}')

try:
    count = ctranslate2.get_cuda_device_count()
    if count > 0:
        import ctypes
        for dll in ['cublas64_12.dll', 'cublas64_11.dll']:
            try:
                ctypes.CDLL(dll)
                print(f'CUDA DLL 利用中: {dll}')
                break
            except:
                pass
except:
    print('CUDA デバイスなし (CPU 動作)')
" 2>&1 | Select-String -NotMatch "WARNING: Ignoring invalid distribution"
    Write-Host $check
    Write-Success "すべてのパッケージが正常にインポートできました"
} catch {
    Write-Warn "インポート確認でエラー: $_"
}

# ------------------------------------------------------------
# 6. サマリー表示
# ------------------------------------------------------------
Write-Step "セットアップ完了"
Write-Host @"

  [*] 構成: $configLabel
  [*] 実行方法: python video_summarizer.py
  [*] ffmpeg: 確認済み

"@ -ForegroundColor Green

if ($configLabel -like "CPU*" -and $det.has_nvidia) {
    Write-Host @"
  [!] ヒント: GPU 検出済みですが CUDA Runtime DLL が見つかりません。
      CUDA Toolkit をインストールして再実行すると GPU で高速動作します。
      ダウンロード: https://developer.nvidia.com/cuda-downloads

"@ -ForegroundColor Yellow
}
