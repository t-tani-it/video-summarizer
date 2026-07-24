"""
動画要約ツール (Video Summarizer)

概要:
    ローカルPC上の動画ファイルから音声を抽出し、文字起こし・要約するGUIアプリ。

用途:
    ・講義や会議の録画をテキスト化して内容把握
    ・動画の内容を簡潔にまとめて共有
    ・長い動画から重要なポイントだけ抽出

前提条件:
    - Python 3.8+
    - ffmpeg (PATH必須: winget install ffmpeg)
    - pip install faster-whisper janome
    - NVIDIA GPU (任意: なくてもCPU動作可)

出力:
    動画と同じフォルダに [ファイル名]_summary.txt
    ・文字起こし全文（タイムスタンプ付き）
    ・TextRankによる抽出型要約
"""

import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import subprocess
import os
import time
import sys

WHISPER_MODEL_SIZE = "large-v3"


def _find_ffmpeg():
    # ffmpegがコマンドとして使えるか確認する
    # CREATE_NO_WINDOW で余計な黒い窓を表示しない
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return "ffmpeg"
    except FileNotFoundError:
        raise RuntimeError("ffmpeg が見つかりません。winget install ffmpeg でインストールしてください。")


FFMPEG_PATH = _find_ffmpeg()


class VideoSummarizerApp:
    # ffmpeg(音声抽出) → faster-whisper(文字起こし) → TextRank(要約) を逐次実行するメインクラス
    def __init__(self, root):
        self.root = root
        self.root.title("動画要約ツール")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        self.video_path = tk.StringVar()
        self.status_text = tk.StringVar(value="準備完了")
        self.is_running = False

        self._build_ui()

    def _build_ui(self):
        main_frame = tk.Frame(self.root, padx=12, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        file_frame = tk.LabelFrame(main_frame, text="動画ファイル選択", padx=8, pady=8)
        file_frame.pack(fill=tk.X, pady=(0, 8))

        path_frame = tk.Frame(file_frame)
        path_frame.pack(fill=tk.X)

        self.path_entry = tk.Entry(path_frame, textvariable=self.video_path, state="readonly")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.select_btn = tk.Button(path_frame, text="ファイルを選択", command=self.select_file, width=14)
        self.select_btn.pack(side=tk.RIGHT)

        control_frame = tk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 8))

        self.run_btn = tk.Button(
            control_frame, text="実行開始", command=self.start_pipeline,
            bg="#4CAF50", fg="white", font=("", 11, "bold"), padx=20, pady=4
        )
        self.run_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = tk.Label(
            control_frame, textvariable=self.status_text,
            anchor=tk.W, fg="#555"
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        log_frame = tk.LabelFrame(main_frame, text="処理ログ", padx=8, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 10),
            state="disabled", bg="#f5f5f5"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        # ログエリアにタイムスタンプ付きでメッセージを追記する
        # update_idletasks で即座にGUI描画を反映
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def select_file(self):
        path = filedialog.askopenfilename(
            title="動画ファイルを選択",
            filetypes=[
                ("動画ファイル", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
                ("すべてのファイル", "*.*")
            ]
        )
        if path:
            self.video_path.set(path)

    def set_ui_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.select_btn.configure(state=state)
        self.run_btn.configure(state=state)

    def start_pipeline(self):
        # バリデーション後、別スレッドでパイプラインを開始
        # メインスレッドをブロックせずGUIを応答可能に保つ
        if not self.video_path.get():
            messagebox.showwarning("警告", "動画ファイルを選択してください。")
            return
        if self.is_running:
            return

        self.is_running = True
        self.set_ui_enabled(False)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        # 3ステップ(音声抽出→文字起こし→要約)のパイプライン本体
        # 一時WAVファイルは finally で確実に削除
        video = self.video_path.get()
        base = os.path.splitext(video)[0]
        wav_path = base + "_audio_temp.wav"
        output_path = base + "_summary.txt"

        try:
            self.status_text.set("音声抽出中...")
            self.log("[1/3] ffmpeg で音声抽出開始")
            self._extract_audio(video, wav_path)
            self.log("[1/3] 音声抽出完了")

            self.status_text.set("文字起こし中...")
            self.log("[2/3] faster-whisper で文字起こし開始")
            segments = self._transcribe(wav_path)
            self.log("[2/3] 文字起こし完了")

            full_text = "\n".join(
                f"[{self._fmt_sec(s.start)} -> {self._fmt_sec(s.end)}] {s.text.strip()}"
                for s in segments
            )

            self.status_text.set("要約生成中...")
            self.log("[3/3] transformers で要約生成開始")
            summary = self._summarize_with_transformers(full_text)
            self.log("[3/3] 要約生成完了")

            with open(output_path, "w", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write("文字起こし全文\n")
                f.write("=" * 60 + "\n\n")
                f.write(full_text)
                f.write("\n\n")
                f.write("=" * 60 + "\n")
                f.write("要約\n")
                f.write("=" * 60 + "\n\n")
                f.write(summary)

            self.log(f"--- 保存完了: {output_path}")
            self.status_text.set("完了")
            self.log("\n===== 要約結果 =====\n")
            self.log(summary)
            messagebox.showinfo("完了", f"処理が完了しました。\n出力ファイル: {output_path}")

        except Exception as e:
            self.log(f"!! エラー: {e}")
            self.status_text.set(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))

        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass
            self.is_running = False
            self.set_ui_enabled(True)

    def _extract_audio(self, video_path, wav_path):
        # ffmpegで動画から音声を抽出
        # 16kHz モノラル WAV はWhisper推奨の入力フォーマット
        cmd = [
            FFMPEG_PATH, "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            wav_path
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {proc.stderr.strip()}")

    def _transcribe(self, audio_path):
        # faster-whisper で音声認識
        # CUDA有無を自動判定しGPU/CPUを切り替え
        # large-v3モデル（日本語に最適）は初回起動時に自動ダウンロード(~3GB)
        try:
            import ctranslate2
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False

        device = "cuda" if has_cuda else "cpu"
        compute = "int8_float16" if has_cuda else "int8"
        self.log(f"   認識デバイス: {'GPU (CUDA)' if has_cuda else 'CPU'}")

        model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=device,
            compute_type=compute,
            download_root=os.path.join(os.path.dirname(__file__), "models")
        )
        segments, info = model.transcribe(audio_path, language="ja", beam_size=3)
        self.log(f"   検出言語: {info.language} (確度: {info.language_probability:.2f})")
        return list(segments)

    def _summarize_with_transformers(self, text):
        # 文字起こし全文から重要文を抽出して要約する
        # 教師なしの TextRank を使用（LLM不要、軽量）
        self.log("   TextRank 抽出型要約を実行中...")
        return self._textrank_summarize(text)

    def _textrank_summarize(self, text, ratio=0.3, min_sents=5):
        # TextRank: 文をノード、単語の重なりをエッジ重みとするグラフにPageRankを適用
        # janomeで形態素解析し、名詞/動詞/形容詞を特徴語として抽出
        from janome.tokenizer import Tokenizer
        import math

        tokenizer = Tokenizer()

        sents = self._split_sentences(text)
        if len(sents) <= 3:
            return text

        self.log(f"   {len(sents)} 文を解析中...")

        def get_words(s):
            return [t.surface for t in tokenizer.tokenize(s)
                    if t.part_of_speech.startswith("名詞")
                    or t.part_of_speech.startswith("動詞")
                    or t.part_of_speech.startswith("形容詞")]

        sent_words = [get_words(s) for s in sents]
        n = len(sents)

        # 文間類似度行列を計算（PageRankの遷移確率として利用）
        # 類似度 = 共通単語数 ÷ (各文の長さの対数和) — 文長の正規化のため対数を使用
        similarity = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                sw = set(sent_words[i]) & set(sent_words[j])
                if not sw:
                    sim = 0.0
                else:
                    sim = len(sw) / (math.log(len(sent_words[i]) + 1) + math.log(len(sent_words[j]) + 1) + 1e-8)
                similarity[i][j] = similarity[j][i] = sim

        # PageRank 反復: d=0.85 は damping factor（標準値）
        scores = [1.0 / n] * n
        d = 0.85
        for _ in range(50):
            prev = scores[:]
            for i in range(n):
                total = 0.0
                for j in range(n):
                    if i != j:
                        row_sum = sum(similarity[j])
                        if row_sum > 0:
                            total += similarity[j][i] * prev[j] / row_sum
                scores[i] = (1 - d) / n + d * total

        ranked = sorted(
            [(scores[i], sents[i]) for i in range(n)],
            key=lambda x: -x[0]
        )

        num_summary = max(min_sents, int(n * ratio))
        if num_summary > n:
            num_summary = n
        selected = sorted(
            ranked[:num_summary], key=lambda x: sents.index(x[1])
        )

        return "\n".join(s for _, s in selected)

    @staticmethod
    def _split_sentences(text):
        # 日本語の句点（。！？）と改行で文単位に分割
        import re
        raw = re.split(r"(?<=[。！？\n])", text)
        result = []
        for s in raw:
            s = s.strip()
            if s:
                result.append(s)
        return result if result else [text]

    @staticmethod
    def _fmt_sec(seconds):
        # 秒数(浮動小数点)を "MM:SS" または "HH:MM:SS" 形式に変換
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoSummarizerApp(root)
    root.mainloop()
