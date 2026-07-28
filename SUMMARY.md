# Video Summarizer - 調整の全体まとめ

## なぜ最初 GPU が使えなかったのか

原因の連鎖:

1. **ctranslate2 4.x (CUDA 12用)** がインストールされていたが、`cublas64_12.dll` がシステムに存在せず、GPU は CUDA 11 までしか対応していなかった（GTX 1050 Ti, Pascal cc 6.1）
2. CUDA 11 用に **ctranslate2 3.24.0 + faster-whisper 0.10.1** にダウングレードし `cublas64_11.dll` を発見 → GPU 認識成功
3. しかし `int8_float16` / `float16` が Pascal で非対応のため無駄な試行が発生
4. **large-v3 (~3.5GB)** が GTX 1050 Ti 4GB に収まらず、推論バッファ確保で OOM → CPU フォールバック
5. `del model + gc.collect()` でも VRAM が解放されず（CUDA ドライバはプロセス生存中にメモリを保持）

## 施した処置の一覧

| # | 問題 | 処置 | 効果 |
|---|------|------|------|
| 1 | `cublas64_12.dll` 不在 | CUDA DLL 検出（12 → 11 → CPU）を実装 | CUDA 11 で GPU 認識 |
| 2 | `int8_float16/float16` 非対応 | compute capability 判定を追加（cc < 7.0 → int8 のみ） | 無駄な試行を排除 |
| 3 | large-v3 OOM | モデル自動フォールバック（large-v3 → medium） | VRAM 1.5GB で安定動作 |
| 4 | チャンク間 VRAM 残留 | 当初は子プロセス方式で対応 → medium で解決したため分割廃止 | シンプル・高速に |
| 5 | WinError 1314 symlink | `HF_HUB_DISABLE_SYMLINKS=1` | モデルダウンロード成功 |
| 6 | 進捗が不明 | プログレスモニター（3分間隔）を追加 | ユーザーが状況把握可能に |
| 7 | 文字化けログ | UTF-8 強制出力 | ログ正常表示 |
| 8 | 環境不一致に気づけない | `_check_environment()` 起動時チェック | 設定ミスを即座に通知 |
| 9 | セットアップが煩雑 | `setup.ps1` 自動セットアップ | GPU に応じてパッケージ自動選択 |

## 最終的な実行環境

| 項目 | 値 |
|------|-----|
| GPU | GTX 1050 Ti (Pascal, 4GB) |
| CUDA | 11.2 (Toolkit) |
| ctranslate2 | 3.24.0 |
| faster-whisper | 0.10.1 |
| モデル | **medium** (1.5GB, int8) |
| 処理方式 | **分割なし、インメモリ** |
| 所要時間（30分動画） | **約5〜7分**（当初の CPU 時 23分から約1/4） |

## 改善率

```
GPU 未使用 (CPU, 23分) ──────────────────────●
                                               |
medium + GPU + インメモリ (5〜7分) ────────────● 約4倍高速化

モデル品質: large-v3(CPU) < medium(GPU)  ← 実効精度も向上
```
