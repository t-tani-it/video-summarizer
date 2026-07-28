# Video Summarizer プロジェクトガイド

このフォルダを読み込んだら、最初に `SUMMARY.md` を読んでください。
プロジェクトの経緯・設定・トラブルシューティングが記載されています。

## クイックスタート

```powershell
.\setup.ps1
python video_summarizer.py
```

## 重要な設定

- **モデル**: `WHISPER_MODEL_SIZE = "medium"` 固定（`video_summarizer.py:36`）
- **チャンク分割**: なし（インメモリ方式、モデル読み込みは1回のみ）
- **フォールバック順**: CUDA 12 → CUDA 11 → CPU
- **Compute Type**: Pascal (cc < 7.0) は `int8` のみ、Volta+ は全種試行
- **プローブ**: 起動時に子プロセスで large-v3 → medium の順にモデル読込可否を確認

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `video_summarizer.py` | メインアプリケーション |
| `setup.ps1` | 自動セットアップスクリプト |
| `SUMMARY.md` | 調整の経緯と全体まとめ |
| `AGENTS.md` | このファイル（プロジェクトガイド） |
| `models/` | Whisper モデルキャッシュ |

## トラブルシューティング

- **WinError 1314**: 自動設定済み (`HF_HUB_DISABLE_SYMLINKS=1`)
- **CUDA OOM**: プローブが自動検出し medium にフォールバック
- **環境不一致**: 起動時に `_check_environment()` が警告表示
