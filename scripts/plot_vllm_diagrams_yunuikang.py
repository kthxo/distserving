#!/usr/bin/env python3
"""슬라이드용 개념 다이어그램 2종 (GPU 0장, 코드 근거만 시각화).

  figures/vllm_iteration_anatomy.png  vLLM V1 한 iteration의 토큰 예산 구성
  figures/vllm_where_queue.png        tr vs default — '어디서 줄 서는가'
"""
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FIG = "/home/yunuikang/yunuikang_work/distserving/figures"
os.makedirs(FIG, exist_ok=True)


def box(ax, x, y, w, h, text, fc, ec="#2c3e50", fs=9, tc="white", lw=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, zorder=3, weight="bold")


# ---------------------------------------------- 1. iteration anatomy
def fig_iteration():
    fig, ax = plt.subplots(figsize=(12.4, 5.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5.6); ax.axis("off")
    ax.text(5, 5.32, "vLLM V1: one scheduler iteration  (scheduler.py:390-399  \"no decoding phase nor prefill phase\")",
            ha="center", fontsize=12.5, weight="bold")
    ax.text(5, 4.95, "token_budget = max_num_batched_tokens = 2048   (RTX4090, 24GB < 70GiB -> arg_utils.py:2414-2423)",
            ha="center", fontsize=9.5, color="#7f8c8d")

    # budget bar
    y0, h = 3.6, 0.72
    ax.text(0.05, y0 + h + 0.22, "STEP 1 — RUNNING first (scheduler.py:432)", fontsize=9.5, weight="bold", color="#2c3e50")
    box(ax, 0.05, y0, 0.34, h, "d", "#c0392b", fs=8)
    box(ax, 0.41, y0, 0.34, h, "d", "#c0392b", fs=8)
    box(ax, 0.77, y0, 8.0, h, "prefill CHUNK of ONE request  (fills the rest of the budget)", "#2980b9", fs=10)
    ax.annotate("", xy=(0.05, y0 - 0.22), xytext=(8.77, y0 - 0.22),
                arrowprops=dict(arrowstyle="<->", color="#2c3e50", lw=1.1))
    ax.text(4.4, y0 - 0.48, "2048 tokens", ha="center", fontsize=9, color="#2c3e50")
    ax.text(9.0, y0 + h / 2, "d = decode\n(1 token each)", fontsize=8, color="#c0392b", va="center")

    # consequence
    y1 = 2.35
    ax.text(0.05, y1 + 0.62, "CONSEQUENCE — TraceLab prompt = 18,684 tok (mean)", fontsize=9.5, weight="bold", color="#2c3e50")
    for i in range(10):
        box(ax, 0.05 + i * 0.88, y1, 0.8, 0.42, f"{i+1}", "#2980b9", fs=8)
    ax.text(9.0, y1 + 0.21, "~10 iterations\nfor ONE prefill", fontsize=8.5, color="#2980b9", va="center", weight="bold")

    # step2
    y2 = 1.25
    ax.text(0.05, y2 + 0.62, "STEP 2 — then WAITING (scheduler.py:626)", fontsize=9.5, weight="bold", color="#2c3e50")
    box(ax, 0.05, y2, 2.5, 0.5, "peek head (not pop!)  :636", "#7f8c8d", fs=8.5)
    box(ax, 2.75, y2, 2.5, 0.5, "get_computed_blocks -> record()  :710", "#e67e22", fs=8.5)
    box(ax, 5.45, y2, 2.2, 0.5, "allocate_slots  :874", "#7f8c8d", fs=8.5)
    box(ax, 7.85, y2, 2.05, 0.5, "None -> break  :888", "#c0392b", fs=8.5)
    ax.add_patch(FancyArrowPatch((8.85, y2), (3.9, y2 - 0.45), connectionstyle="arc3,rad=0.28",
                                 arrowstyle="-|>", color="#c0392b", lw=1.6, mutation_scale=13, zorder=4))
    ax.text(6.2, y2 - 0.62, "stays at queue head, num_computed_tokens still 0 (:1141)\n"
                            "-> re-records EVERY step  =>  queries inflate up to 30x",
            ha="center", fontsize=8.6, color="#c0392b", weight="bold")
    fig.tight_layout()
    p = f"{FIG}/vllm_iteration_anatomy.png"
    fig.savefig(p, dpi=150); plt.close(fig); print("wrote", p)


# ---------------------------------------------- 2. where do they queue
def fig_where_queue():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.9))
    cfg = [
        ("tr   (R = 0.31 < 1)", "#2e86ab",
         [("PAUSED\nproxy queue", "#8e44ad", "pause_s = 18.47 s/step\n(profiler SEES it)"),
          ("vLLM waiting", "#bdc3c7", "REASONING - nrr = 0.11\n(almost none)"),
          ("GPU running", "#c0392b", "nrr = 0.38,  batch 1.19\nU = 0.32")]),
        ("default   (R = 1.20 > 1)", "#c0392b",
         [("PAUSED\nproxy queue", "#bdc3c7", "pause_s = 0.00 s\n(nothing here)"),
          ("vLLM waiting", "#8e44ad", "REASONING - nrr = 3.32\n(profiler BLIND)"),
          ("GPU running", "#c0392b", "nrr = 1.24,  batch 1.45\nU = 0.86")]),
    ]
    for ax, (title, tc, stages) in zip(axes, cfg):
        ax.set_xlim(0, 10); ax.set_ylim(0, 8.4); ax.axis("off")
        ax.text(5, 8.0, title, ha="center", fontsize=13, weight="bold", color=tc)
        y = 6.3
        for name, color, note in stages:
            box(ax, 0.5, y, 3.9, 1.25, name, color, fs=10.5)
            ax.text(4.75, y + 0.62, note, fontsize=8.8, va="center", color="#2c3e50")
            if y > 2.7:
                ax.add_patch(FancyArrowPatch((2.45, y), (2.45, y - 0.62),
                                             arrowstyle="-|>", color="#2c3e50", lw=1.5, mutation_scale=12))
            y -= 1.87
        ax.text(5, 0.55, "same workload, same tool time (6.0 s)\nthe ONLY difference is WHERE the queue is",
                ha="center", fontsize=9, style="italic", color="#7f8c8d")
    fig.suptitle("tr and default both queue — they differ in WHERE  (expC, 2x4090, TraceLab C=16)",
                 fontsize=12.5, weight="bold")
    fig.tight_layout()
    p = f"{FIG}/vllm_where_queue.png"
    fig.savefig(p, dpi=150); plt.close(fig); print("wrote", p)


if __name__ == "__main__":
    fig_iteration(); fig_where_queue()
