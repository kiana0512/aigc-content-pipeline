# fix_comfyui_pos_gui.py
# -*- coding: utf-8 -*-
"""
ComfyUI Workflow 节点坐标修复 GUI 工具

功能：
1. 选择一个 ComfyUI workflow JSON 文件
2. 自动读取所有 nodes[*].pos
3. 将异常大的坐标统一缩放回正常范围
4. 可手动设置 canvas_width / canvas_height / padding
5. 可选择是否以 (0,0) 为中心
6. 可选择是否生成 .bak 备份
7. 确认后直接覆盖原始 JSON 文件

运行：
python fix_comfyui_pos_gui.py
"""

from __future__ import annotations

import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, List, Tuple


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def collect_positions(nodes: List[dict]) -> List[Tuple[int, float, float]]:
    """
    收集所有有效节点坐标。
    返回：
        [(node_index, x, y), ...]
    """
    positions: List[Tuple[int, float, float]] = []

    for idx, node in enumerate(nodes):
        pos = node.get("pos")

        if not isinstance(pos, list) or len(pos) < 2:
            continue

        try:
            x = float(pos[0])
            y = float(pos[1])
        except (TypeError, ValueError):
            continue

        positions.append((idx, x, y))

    return positions


def normalize_positions(
    nodes: List[dict],
    canvas_width: float,
    canvas_height: float,
    padding: float,
    center_origin: bool,
    round_digits: int = 2,
) -> dict:
    """
    只修改 nodes[*].pos，不改其他字段。

    算法：
    1. 计算所有节点原始坐标包围盒
    2. 按比例缩放到目标画布范围
    3. 保持相对布局关系
    4. 可选整体移动到以 (0,0) 为中心
    """
    positions = collect_positions(nodes)

    if not positions:
        raise ValueError("当前 JSON 中没有找到有效的 nodes[*].pos 坐标。")

    xs = [x for _, x, _ in positions]
    ys = [y for _, _, y in positions]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    usable_w = max(canvas_width - 2 * padding, 100.0)
    usable_h = max(canvas_height - 2 * padding, 100.0)

    scale = min(usable_w / span_x, usable_h / span_y)

    new_coords: List[Tuple[float, float]] = []

    for _, x, y in positions:
        nx = (x - min_x) * scale + padding
        ny = (y - min_y) * scale + padding
        new_coords.append((nx, ny))

    if center_origin:
        new_xs = [x for x, _ in new_coords]
        new_ys = [y for _, y in new_coords]

        cx = (min(new_xs) + max(new_xs)) / 2.0
        cy = (min(new_ys) + max(new_ys)) / 2.0

        new_coords = [(x - cx, y - cy) for x, y in new_coords]

    for (node_idx, _, _), (nx, ny) in zip(positions, new_coords):
        original_pos = nodes[node_idx].get("pos")

        new_pos = [round(nx, round_digits), round(ny, round_digits)]

        # 如果 pos 后面还有额外元素，保留它们
        if isinstance(original_pos, list) and len(original_pos) > 2:
            nodes[node_idx]["pos"] = new_pos + original_pos[2:]
        else:
            nodes[node_idx]["pos"] = new_pos

    return {
        "node_count": len(positions),
        "original_min_x": min_x,
        "original_max_x": max_x,
        "original_min_y": min_y,
        "original_max_y": max_y,
        "original_span_x": span_x,
        "original_span_y": span_y,
        "scale": scale,
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
        "padding": padding,
        "center_origin": center_origin,
    }


class ComfyPosFixerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ComfyUI Workflow Pos 修复工具")
        self.root.geometry("720x520")
        self.root.resizable(False, False)

        self.file_path_var = tk.StringVar(value="")
        self.canvas_width_var = tk.StringVar(value="5000")
        self.canvas_height_var = tk.StringVar(value="3000")
        self.padding_var = tk.StringVar(value="100")
        self.center_origin_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self) -> None:
        title = tk.Label(
            self.root,
            text="ComfyUI Workflow 节点坐标 pos 修复工具",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        title.pack(pady=(18, 8))

        desc = tk.Label(
            self.root,
            text="选择一个 workflow JSON，设置目标画布范围，然后直接覆盖原文件。仅修改 nodes[*].pos。",
            font=("Microsoft YaHei UI", 10),
            fg="#444444",
        )
        desc.pack(pady=(0, 14))

        file_frame = tk.Frame(self.root)
        file_frame.pack(fill="x", padx=24, pady=8)

        tk.Label(file_frame, text="Workflow JSON：", width=16, anchor="w").pack(side="left")

        file_entry = tk.Entry(file_frame, textvariable=self.file_path_var, width=62)
        file_entry.pack(side="left", padx=(0, 8))

        browse_btn = tk.Button(file_frame, text="选择文件", command=self.choose_file)
        browse_btn.pack(side="left")

        params_frame = tk.LabelFrame(self.root, text="坐标修复参数", padx=16, pady=12)
        params_frame.pack(fill="x", padx=24, pady=16)

        row1 = tk.Frame(params_frame)
        row1.pack(fill="x", pady=6)

        tk.Label(row1, text="canvas_width：", width=16, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=self.canvas_width_var, width=16).pack(side="left", padx=(0, 24))

        tk.Label(row1, text="canvas_height：", width=16, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=self.canvas_height_var, width=16).pack(side="left")

        row2 = tk.Frame(params_frame)
        row2.pack(fill="x", pady=6)

        tk.Label(row2, text="padding：", width=16, anchor="w").pack(side="left")
        tk.Entry(row2, textvariable=self.padding_var, width=16).pack(side="left", padx=(0, 24))

        tk.Checkbutton(
            row2,
            text="以 (0,0) 为中心",
            variable=self.center_origin_var,
        ).pack(side="left", padx=(0, 24))

        tk.Checkbutton(
            row2,
            text="覆盖前生成 .bak 备份",
            variable=self.backup_var,
        ).pack(side="left")

        tips = tk.Label(
            params_frame,
            text=(
                "说明：默认会把所有节点缩放到 5000×3000 的正常画布范围内，"
                "保持节点之间的相对布局关系。"
            ),
            fg="#666666",
            anchor="w",
            justify="left",
        )
        tips.pack(fill="x", pady=(10, 0))

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=24, pady=8)

        preview_btn = tk.Button(
            btn_frame,
            text="预览坐标范围",
            width=18,
            command=self.preview_info,
        )
        preview_btn.pack(side="left", padx=(0, 12))

        fix_btn = tk.Button(
            btn_frame,
            text="修复并覆盖原文件",
            width=22,
            bg="#2d7d46",
            fg="white",
            command=self.fix_and_overwrite,
        )
        fix_btn.pack(side="left")

        self.log_text = tk.Text(self.root, height=12, width=88)
        self.log_text.pack(padx=24, pady=(10, 16))

        self._log("等待选择 ComfyUI workflow JSON 文件。")

    def _log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 ComfyUI workflow JSON",
            filetypes=[
                ("JSON 文件", "*.json"),
                ("所有文件", "*.*"),
            ],
        )

        if path:
            self.file_path_var.set(path)
            self._log(f"已选择文件：{path}")

    def _get_selected_path(self) -> Path:
        raw = self.file_path_var.get().strip()

        if not raw:
            raise ValueError("请先选择 workflow JSON 文件。")

        path = Path(raw)

        if not path.exists():
            raise ValueError(f"文件不存在：{path}")

        if path.suffix.lower() != ".json":
            raise ValueError("请选择 .json 文件。")

        return path

    def _get_params(self) -> tuple[float, float, float, bool]:
        try:
            canvas_width = float(self.canvas_width_var.get().strip())
            canvas_height = float(self.canvas_height_var.get().strip())
            padding = float(self.padding_var.get().strip())
        except ValueError:
            raise ValueError("canvas_width / canvas_height / padding 必须是数字。")

        if canvas_width <= 0:
            raise ValueError("canvas_width 必须大于 0。")

        if canvas_height <= 0:
            raise ValueError("canvas_height 必须大于 0。")

        if padding < 0:
            raise ValueError("padding 不能小于 0。")

        if padding * 2 >= canvas_width or padding * 2 >= canvas_height:
            raise ValueError("padding 太大，不能超过画布宽高的一半。")

        return (
            canvas_width,
            canvas_height,
            padding,
            self.center_origin_var.get(),
        )

    def preview_info(self) -> None:
        try:
            path = self._get_selected_path()
            data = load_json(path)

            nodes = data.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError("这个 JSON 不是有效的 ComfyUI workflow：缺少 nodes 列表。")

            positions = collect_positions(nodes)
            if not positions:
                raise ValueError("没有找到有效节点坐标。")

            xs = [x for _, x, _ in positions]
            ys = [y for _, _, y in positions]

            self._log("========== 当前坐标范围 ==========")
            self._log(f"节点数量：{len(positions)}")
            self._log(f"x 范围：{min(xs)}  ->  {max(xs)}")
            self._log(f"y 范围：{min(ys)}  ->  {max(ys)}")
            self._log(f"x span：{max(xs) - min(xs)}")
            self._log(f"y span：{max(ys) - min(ys)}")
            self._log("=================================")

        except Exception as e:
            messagebox.showerror("预览失败", str(e))
            self._log(f"[ERROR] 预览失败：{e}")

    def fix_and_overwrite(self) -> None:
        try:
            path = self._get_selected_path()
            canvas_width, canvas_height, padding, center_origin = self._get_params()

            confirm_text = (
                "即将直接覆盖原始 workflow JSON 文件。\n\n"
                f"文件：\n{path}\n\n"
                f"canvas_width：{canvas_width}\n"
                f"canvas_height：{canvas_height}\n"
                f"padding：{padding}\n"
                f"center_origin：{center_origin}\n"
                f"生成备份：{self.backup_var.get()}\n\n"
                "确认继续吗？"
            )

            if not messagebox.askyesno("确认覆盖原文件", confirm_text):
                self._log("用户取消覆盖。")
                return

            data = load_json(path)

            nodes = data.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError("这个 JSON 不是有效的 ComfyUI workflow：缺少 nodes 列表。")

            if self.backup_var.get():
                backup_path = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup_path)
                self._log(f"已生成备份：{backup_path}")

            stats = normalize_positions(
                nodes=nodes,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                padding=padding,
                center_origin=center_origin,
                round_digits=2,
            )

            save_json(path, data)

            self._log("========== 修复完成 ==========")
            self._log(f"已覆盖原文件：{path}")
            self._log(f"节点数量：{stats['node_count']}")
            self._log(
                f"原始 x 范围：{stats['original_min_x']} -> {stats['original_max_x']}"
            )
            self._log(
                f"原始 y 范围：{stats['original_min_y']} -> {stats['original_max_y']}"
            )
            self._log(f"缩放比例：{stats['scale']}")
            self._log("=============================")

            messagebox.showinfo(
                "修复完成",
                "所有节点 pos 已修复，并已覆盖原始 JSON 文件。",
            )

        except Exception as e:
            messagebox.showerror("修复失败", str(e))
            self._log(f"[ERROR] 修复失败：{e}")


def main() -> None:
    root = tk.Tk()
    app = ComfyPosFixerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()