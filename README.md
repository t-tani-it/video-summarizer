# Video Summarizer (動画要約ツール)

ローカルPC上の動画ファイルの内容をテキストに要約する無料システム。

## 仕組み

```
動画ファイル (mp4, avi, mkv, mov 等)
    ↓ ffmpeg
WAV (16kHz モノラル)
    ↓ faster-whisper (large-v3)
文字起こし全文 (タイムスタンプ付き)
    ↓ TextRank (janome)
抽出型要約
```

## 必要な環境

- Python 3.8+
- NVIDIA GPU (CUDA, 4GB VRAM以上推奨) — なくてもCPU動作可
- ffmpeg (winget install ffmpeg または https://ffmpeg.org から)

## インストール

```bash
pip install faster-whisper janome
winget install ffmpeg    # Windows
```

## 使い方

```bash
python video_summarizer.py
```

GUI が開くので「ファイルを選択」→「実行開始」で動画を選ぶだけ。  
動画と同じフォルダに `[ファイル名]_summary.txt` が出力されます。

### 出力内容

```
============================================================
文字起こし全文
============================================================

[00:00 -> 00:12] ...
[00:12 -> 00:25] ...
...

============================================================
要約
============================================================

(TextRank で抽出された重要文)
```

## 技術スタック（すべて無料・ローカル完結）

| 機能 | ツール | 備考 |
|------|--------|------|
| 音声抽出 | ffmpeg | あらゆる動画形式対応 |
| 音声認識 | faster-whisper (large-v3) | OpenAI Whisper の高速実装。GPU対応。30分動画で約10〜20分 |
| 言語解析 | janome | 日本語形態素解析 (純Python) |
| 要約 | TextRank | 教師なしグラフベースの抽出型要約。学習不要。 |
| GUI | tkinter | Python標準。追加インストール不要。 |

## PCスペックと処理時間の関係

### 各処理の負荷一覧

| 処理 | 負荷要素 | 所要時間の目安 |
|------|----------|---------------|
| ffmpeg 音声抽出 | CPU | 動画の5〜10%程度（瞬時） |
| Whisper 文字起こし | GPU/VRAM が最重要 | 30分動画で GPU: 10〜20分, CPU: 30〜60分 |
| TextRank 要約 | CPU/RAM | 数千文でも数秒 |

### GPU と処理時間の早見表（30分動画基準）

| GPU | VRAM | Whisperモデル | 所要時間目安 |
|-----|------|-------------|------------|
| なし (CPU) | — | small | 30〜60分 |
| GTX 1050 Ti | 4GB | large-v3 (int8) | 10〜20分 |
| RTX 3060 | 12GB | large-v3 (float16) | 3〜5分 |
| RTX 4090 | 24GB | large-v3 (float16) | 1〜2分 |

### 動画の長さごとの推奨スペック

| 動画時間 | 最小スペック | 推奨スペック |
|----------|------------|------------|
| 〜15分 | CPU 4コア, RAM 4GB | GPU 4GB VRAM, RAM 8GB |
| 15〜60分 | GPU 4GB VRAM, RAM 8GB | GPU 6GB+ VRAM, RAM 16GB |
| 1〜3時間 | GPU 6GB VRAM, RAM 16GB | GPU 8GB+ VRAM, RAM 16GB+ |
| 3時間〜 | GPU 8GB+ VRAM, RAM 16GB+ | GPU 12GB+ VRAM, RAM 32GB |

### 使用モデルについて

このツールは **faster-whisper** の **large-v3** モデルを使用しています。

| 項目 | 内容 |
|------|------|
| モデル | large-v3 (OpenAI Whisper) |
| サイズ | 約3GB |
| VRAM目安 | 約4GB（int8量子化時） |
| 初回起動時 | 自動ダウンロード（`models/` フォルダにキャッシュ） |
| 対応言語 | 日本語、英語、他90言語以上 |
| 認識精度 | Whisperシリーズ中、最高精度 |
| 備考 | GPUメモリが不足する場合、`video_summarizer.py` 先頭の `WHISPER_MODEL_SIZE` を `"small"` や `"medium"` に変更すると軽量になる |

### モデルサイズ選択による調整（参考）

`WHISPER_MODEL_SIZE` の値を変更することで、スペックに応じたモデルを選択できます。

| モデル | サイズ | VRAM目安 | 精度 | CPU時速度の目安 |
|--------|--------|---------|------|---------------|
| tiny | 75MB | 〜1GB | 低 | 実時間の2〜3倍 |
| base | 150MB | 〜1GB | やや低 | 実時間の1.5〜2倍 |
| small | 500MB | 〜2GB | 中 | 実時間と同程度 |
| medium | 1.5GB | 〜3GB | 高い | 実時間の2倍程度 |
| large-v3 | 3GB | 〜4GB | 最高 | 実時間の3〜4倍 |

## 制限・補足

### 並列処理について

30分動画2本を連続処理する場合、GPUメモリ (4GB) の制約から2本同時のGPU処理は不可。
以下の方式でオーバーラップ可能だが、本バージョンでは実装していない：

1. **パイプライン処理**: ファイルAの文字起こし（GPU）中にファイルBの音声抽出（CPU）を並列実行
2. **バッチキュー**: 複数ファイルを一度選択し、1本ずつ自動連続実行
3. **要約の並列化**: 文字起こし完了後の要約（CPU）と次の文字起こし（GPU）をオーバーラップ

### DeepSeek / Ollama について

当初は Ollama + deepseek-r1 (8.2B) をローカルLLMとして要約に使用する設計だったが、以下の理由で断念：

- **CUDA互換性問題**: GTX 1050 Ti (Pascal, compute capability 6.1) の場合、Ollama 0.32.3 にバンドルされたCUDA PTXが新しいアーキテクチャ向けにコンパイルされており、`"the provided PTX was compiled with an unsupported toolchain"` エラーが発生
- **回避不能**: `OLLAMA_CUDA=0`, `OLLAMA_CUDA_OVERRIDE_ARCH=1` 等の環境変数でも解決せず、Ollamaプロセスがクラッシュ
- **解決策**: CPU専用の軽量LLMと差し替えるか、LLMを使わないTextRankによる抽出型要約に変更

代替案として以下が考えられる：
- より新しいGPU (Turingアーキテクチャ以上) ではOllamaは正常動作する
- 軽量LLM (`google/mt5-small` 等) を transformers + PyTorch (CPU) で使用（ただし環境によってはnumpy/依存関係の衝突に注意）
