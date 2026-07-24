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
