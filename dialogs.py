"""
dialogs.py — GUI에서 사용하는 모달 다이얼로그 클래스 모음.

포함된 클래스:
  ImageSelectionDialog        — PDF에서 추출한 이미지 중 번역할 항목 선택
  ImagePreviewDialog          — 이미지 글자 제거 전후 비교
  GlossaryEditorDialog        — 용어집 .txt 파일을 테이블 형식으로 편집
  CcfoliaOriginalPickerDialog — 코코포리아 원본 이미지 단일 선택
  CcfoliaImagePairDialog      — 번역본↔원본 이미지 수동 매핑
  CcfoliaAutoConfirmDialog    — 파일명 자동 매칭 결과 확인
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
import os
import sys
import json
from PIL import Image, ImageTk


class ImageSelectionDialog(tk.Toplevel):
    """PDF에서 추출된 이미지 목록을 그리드로 표시하고 번역할 항목을 체크박스로 선택하는 다이얼로그."""

    def __init__(self, parent, images, filename):
        super().__init__(parent)
        self.title(f"이미지 선택 - {filename}")
        self.geometry("900x700")

        self.images = images  # list of dicts: {id, page, image, size, width, height}
        self.selected_ids = []

        # UI Layout
        # Top: Controls
        top_frame = tk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(top_frame, text=f"'{filename}'에서 발견된 이미지 ({len(images)}개):", font=("Arial", 11, "bold")).pack(side="left")

        tk.Button(top_frame, text="모두 선택", command=self.select_all).pack(side="right", padx=5)
        tk.Button(top_frame, text="모두 해제", command=self.deselect_all).pack(side="right", padx=5)

        # Filter Frame
        filter_frame = tk.Frame(self)
        filter_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(filter_frame, text="최소 크기 필터 (px):").pack(side="left")
        self.min_size_var = tk.IntVar(value=100) # Default 100px
        tk.Entry(filter_frame, textvariable=self.min_size_var, width=5).pack(side="left", padx=5)
        tk.Button(filter_frame, text="적용 (작은 이미지 해제)", command=self.apply_filter).pack(side="left", padx=5)

        # Main: Scrollable Canvas for Grid of Images
        self.canvas = tk.Canvas(self, bg="#f0f0f0")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#f0f0f0")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=10)
        self.scrollbar.pack(side="right", fill="y")

        # Bottom: OK/Cancel
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)

        tk.Button(btn_frame, text="선택 완료 (번역 시작)", command=self.on_ok, bg="#4CAF50", fg="white", height=2).pack(fill="x")

        # Variables to track Checkbuttons
        self.check_vars = {} # id -> BooleanVar

        # Populate
        self.populate_images()

        # Make modal
        self.transient(parent)
        self.grab_set()

    def populate_images(self):
        # Clear existing
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        columns = 3
        # Simple Grid
        for i, img_data in enumerate(self.images):
            img_id = img_data['id']
            pil_img = img_data['image']

            # Create a card frame
            card = tk.Frame(self.scrollable_frame, bg="white", relief="ridge", borderwidth=2)
            card.grid(row=i // columns, column=i % columns, padx=10, pady=10, sticky="nsew")

            # Checkbox
            var = tk.BooleanVar(value=True) # Default Checked
            self.check_vars[img_id] = var

            cb = tk.Checkbutton(card, variable=var, bg="white")
            cb.pack(anchor="nw")

            # Thumbnail
            try:
                thumb = pil_img.copy()
                thumb.thumbnail((200, 200))
                tk_thumb = ImageTk.PhotoImage(thumb)

                lbl_img = tk.Label(card, image=tk_thumb, bg="white")
                lbl_img.image = tk_thumb # Keep reference
                lbl_img.pack(pady=5)
            except Exception as e:
                tk.Label(card, text="[이미지 로드 실패]", bg="white").pack()

            # Info
            info_text = f"Page {img_data['page']}\n{img_data['size']}"
            tk.Label(card, text=info_text, bg="white", font=("Arial", 9)).pack(pady=2)

    def select_all(self):
        for var in self.check_vars.values():
            var.set(True)

    def deselect_all(self):
        for var in self.check_vars.values():
            var.set(False)

    def apply_filter(self):
        """최소 크기 미만의 이미지(예: 아이콘, 구분선)를 자동으로 선택 해제한다."""
        min_px = self.min_size_var.get()
        for img_data in self.images:
            w = img_data['width']
            h = img_data['height']
            img_id = img_data['id']

            if w < min_px or h < min_px:
                if img_id in self.check_vars:
                    self.check_vars[img_id].set(False)

    def on_ok(self):
        self.selected_ids = [mid for mid, var in self.check_vars.items() if var.get()]
        self.destroy()


class ImagePreviewDialog(tk.Toplevel):
    """이미지 글자 제거 결과를 원본과 나란히 비교하는 미리보기 다이얼로그."""

    def __init__(self, parent, original_img, cleaned_img, filename):
        super().__init__(parent)
        self.title(f"미리보기 - {filename}")
        self.geometry("1000x600")

        # Set Window Icon
        try:
            def resource_path(relative_path):
                try:
                    base_path = sys._MEIPASS
                except Exception:
                    base_path = os.path.abspath(".")
                return os.path.join(base_path, relative_path)

            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except:
            pass

        # Frames for images
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Original
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True)
        tk.Label(left_frame, text="원본 (Original)", font=("Arial", 10, "bold")).pack(pady=5)

        # Cleaned
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side="left", fill="both", expand=True)
        tk.Label(right_frame, text="제거 후 (Cleaned)", font=("Arial", 10, "bold")).pack(pady=5)

        # Resize for display
        def prepare_display(img):
            display_img = img.copy()
            display_img.thumbnail((480, 500))
            return ImageTk.PhotoImage(display_img)

        self.tk_orig = prepare_display(original_img)
        self.tk_clean = prepare_display(cleaned_img)

        tk.Label(left_frame, image=self.tk_orig).pack()
        tk.Label(right_frame, image=self.tk_clean).pack()

        # Close Button
        tk.Button(self, text="닫기", command=self.destroy, width=20, height=2).pack(pady=10)

        self.transient(parent)
        self.grab_set()


# ── 용어집 내장 편집기 ───────────────────────────────────────────────────

class GlossaryEditorDialog(tk.Toplevel):
    """용어집 파일(.txt)을 테이블 형식으로 편집하는 다이얼로그."""

    def __init__(self, parent, filepath: str):
        super().__init__(parent)
        self.filepath = filepath
        self.title(f"용어집 편집 — {os.path.basename(filepath)}")
        self.geometry("640x480")
        self.resizable(True, True)

        self._build_ui()
        self._load_file()

        self.transient(parent)
        self.grab_set()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # Treeview (원어 | 번역어 두 열)
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self.tree = ttk.Treeview(tree_frame, columns=("jp", "kr"), show="headings", selectmode="browse")
        self.tree.heading("jp", text="원어 (일본어)")
        self.tree.heading("kr", text="번역어 (한국어)")
        self.tree.column("jp", width=280, minwidth=100)
        self.tree.column("kr", width=280, minwidth=100)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 더블클릭 → 행 편집
        self.tree.bind("<Double-1>", self._on_double_click)

        # 버튼 행
        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        tk.Button(btn_row, text="+ 추가", command=self._add_row, bg="#4CAF50", fg="white", width=10).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="- 삭제", command=self._delete_row, bg="#F44336", fg="white", width=10).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="저장", command=self._save_file, bg="#2196F3", fg="white", width=10).pack(side="right")
        tk.Button(btn_row, text="닫기", command=self.destroy, width=10).pack(side="right", padx=(0, 4))

    # ── 파일 입출력 ──────────────────────────────────────────────────────

    def _load_file(self):
        """파일에서 key:value 행을 파싱해 Treeview에 채운다."""
        self.tree.delete(*self.tree.get_children())
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        jp, kr = line.split(":", 1)
                        self.tree.insert("", "end", values=(jp.strip(), kr.strip()))
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("오류", f"파일 읽기 실패:\n{e}", parent=self)

    def _save_file(self):
        """Treeview 내용을 key:value 형식으로 파일에 저장한다."""
        try:
            lines = []
            for iid in self.tree.get_children():
                jp, kr = self.tree.item(iid, "values")
                if jp.strip():
                    lines.append(f"{jp.strip()}:{kr.strip()}\n")
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.writelines(lines)
            from tkinter import messagebox
            messagebox.showinfo("저장 완료", f"저장됨: {os.path.basename(self.filepath)}", parent=self)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("저장 실패", str(e), parent=self)

    # ── 행 조작 ──────────────────────────────────────────────────────────

    def _add_row(self):
        """빈 행 하나를 추가하고 즉시 편집창을 연다."""
        iid = self.tree.insert("", "end", values=("", ""))
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self._open_edit_popup(iid)

    def _delete_row(self):
        selected = self.tree.selection()
        if selected:
            self.tree.delete(selected[0])

    # ── 인라인 편집 팝업 ─────────────────────────────────────────────────

    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self._open_edit_popup(iid)

    def _open_edit_popup(self, iid):
        """선택된 행의 원어/번역어를 편집하는 작은 팝업을 띄운다."""
        jp_val, kr_val = self.tree.item(iid, "values")

        popup = tk.Toplevel(self)
        popup.title("행 편집")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        tk.Label(popup, text="원어 (일본어):").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        jp_var = tk.StringVar(value=jp_val)
        tk.Entry(popup, textvariable=jp_var, width=30).grid(row=0, column=1, padx=8, pady=6)

        tk.Label(popup, text="번역어 (한국어):").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        kr_var = tk.StringVar(value=kr_val)
        tk.Entry(popup, textvariable=kr_var, width=30).grid(row=1, column=1, padx=8, pady=6)

        def apply():
            self.tree.item(iid, values=(jp_var.get().strip(), kr_var.get().strip()))
            popup.destroy()

        btn_f = tk.Frame(popup)
        btn_f.grid(row=2, column=0, columnspan=2, pady=8)
        tk.Button(btn_f, text="확인", command=apply, bg="#4CAF50", fg="white", width=10).pack(side="left", padx=4)
        tk.Button(btn_f, text="취소", command=popup.destroy, width=10).pack(side="left", padx=4)


# ── 코코포리아 이미지 교체 다이얼로그 ────────────────────────────────────


def _make_thumb_tk(pil_img, size=120):
    """PIL Image → ImageTk.PhotoImage (썸네일). 실패 시 None."""
    try:
        img = pil_img.copy()
        img.thumbnail((size, size))
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def _load_pil(path, size=120):
    """경로에서 PIL Image 로드 (썸네일 크기로). 실패 시 None."""
    try:
        img = Image.open(path).convert("RGBA")
        img.thumbnail((size, size))
        return img
    except Exception:
        return None


class CcfoliaOriginalPickerDialog(tk.Toplevel):
    """원본 이미지 목록에서 하나를 선택하는 서브 다이얼로그."""

    _last_geometry = None  # 클래스 변수: 마지막 창 위치/크기 기억

    def __init__(self, parent, src_dir, src_files):
        super().__init__(parent)
        self.title("원본 이미지 선택")
        if CcfoliaOriginalPickerDialog._last_geometry:
            self.geometry(CcfoliaOriginalPickerDialog._last_geometry)
        else:
            self.geometry("760x560")
        self.resizable(True, True)

        self.src_dir = src_dir
        self.src_files = src_files
        self.selected_filename = None   # 선택 결과

        self._tk_refs = []  # PhotoImage GC 방지

        # 상단 안내
        tk.Label(self, text="교체할 원본 이미지를 클릭해 선택하세요.",
                 font=("Arial", 10, "bold")).pack(pady=(8, 4))

        # 스크롤 캔버스
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.canvas = tk.Canvas(frame, bg="#f0f0f0")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg="#f0f0f0")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 마우스 휠 스크롤
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # 하단 취소 버튼
        tk.Button(self, text="취소", command=self._on_close, width=12).pack(pady=6)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._populate()
        self.transient(parent)
        self.grab_set()

    def _on_close(self):
        """창 닫기 — 현재 위치/크기 저장."""
        CcfoliaOriginalPickerDialog._last_geometry = self.geometry()
        self.destroy()

    def _populate(self):
        COLS = 4
        THUMB = 160
        for i, fn in enumerate(self.src_files):
            path = os.path.join(self.src_dir, fn)
            pil = _load_pil(path, THUMB)
            tk_img = _make_thumb_tk(pil, THUMB) if pil else None

            card = tk.Frame(self.inner, bg="white", relief="groove", borderwidth=1,
                            width=THUMB + 20, height=THUMB + 44)
            card.grid(row=i // COLS, column=i % COLS, padx=6, pady=6, sticky="nsew")
            card.pack_propagate(False)

            # 클릭 핸들러
            def _on_click(filename=fn):
                CcfoliaOriginalPickerDialog._last_geometry = self.geometry()
                self.selected_filename = filename
                self.destroy()

            if tk_img:
                self._tk_refs.append(tk_img)
                lbl = tk.Label(card, image=tk_img, bg="white", cursor="hand2")
                lbl.place(x=0, y=0, width=THUMB + 20, height=THUMB + 4)
                lbl.bind("<Button-1>", lambda e, f=fn: _on_click(f))
            else:
                lbl = tk.Label(card, text="[로드 실패]", bg="white", cursor="hand2")
                lbl.place(x=0, y=0, width=THUMB + 20, height=THUMB + 4)
                lbl.bind("<Button-1>", lambda e, f=fn: _on_click(f))

            # 파일명 (해시 앞 8자...뒤 8자)
            short = fn[:8] + "..." + fn[-12:] if len(fn) > 24 else fn
            name_lbl = tk.Label(card, text=short, bg="white",
                                font=("Arial", 7), wraplength=THUMB + 10, cursor="hand2")
            name_lbl.place(x=0, y=THUMB + 6, width=THUMB + 20, height=32)
            name_lbl.bind("<Button-1>", lambda e, f=fn: _on_click(f))
            card.bind("<Button-1>", lambda e, f=fn: _on_click(f))


class CcfoliaImagePairDialog(tk.Toplevel):
    """모드 A: 번역본 이미지 목록에서 각각 원본을 수동으로 매핑하는 다이얼로그."""

    MAPPING_FILE_TYPES = [("매핑 JSON", "*.json"), ("모든 파일", "*.*")]
    THUMB = 180

    def __init__(self, parent, src_dir, src_files, trans_dir, trans_files,
                 initial_mapping=None):
        super().__init__(parent)
        self.title(f"수동 이미지 매핑 — 번역본 {len(trans_files)}개")
        self.geometry("820x640")
        self.resizable(True, True)

        self.src_dir = src_dir
        self.src_files = src_files
        self.trans_dir = trans_dir
        self.trans_files = trans_files

        # {trans_filename: orig_filename or None}
        # initial_mapping이 있으면 API 추천값으로 미리 채움
        if initial_mapping:
            self.mapping = {fn: initial_mapping.get(fn) for fn in trans_files}
        else:
            self.mapping = {fn: None for fn in trans_files}

        self.result_pairs = []     # 최종 반환값: [(trans_path, orig_filename), ...]
        self._tk_refs = []

        self._build_ui()
        self._populate()

        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        # 상단 안내
        tk.Label(self, text="각 번역본 이미지에 대응하는 원본 이미지를 선택하세요.",
                 font=("Arial", 10, "bold")).pack(pady=(8, 2))

        # 스크롤 영역
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.canvas = tk.Canvas(frame, bg="#f5f5f5")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.rows_frame = tk.Frame(self.canvas, bg="#f5f5f5")
        self.rows_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(
                                 scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # 하단 버튼 행
        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=8)

        tk.Button(btn_row, text="매핑 저장", command=self._save_mapping,
                  bg="#607D8B", fg="white", width=10).pack(side="left", padx=4)
        tk.Button(btn_row, text="매핑 불러오기", command=self._load_mapping,
                  bg="#607D8B", fg="white", width=12).pack(side="left", padx=4)

        tk.Button(btn_row, text="취소", command=self.destroy, width=10).pack(side="right", padx=4)
        tk.Button(btn_row, text="확인", command=self._on_ok,
                  bg="#4CAF50", fg="white", width=10).pack(side="right", padx=4)

    def _populate(self):
        """번역본 이미지마다 [번역본 썸네일 → 원본 선택 슬롯] 행을 생성한다."""
        for widget in self.rows_frame.winfo_children():
            widget.destroy()

        T = self.THUMB
        # 헤더
        hdr = tk.Frame(self.rows_frame, bg="#ddd")
        hdr.pack(fill="x", padx=4, pady=(0, 2))
        tk.Label(hdr, text="번역본 이미지", bg="#ddd", width=22,
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)
        tk.Label(hdr, text="→", bg="#ddd", width=3).pack(side="left")
        tk.Label(hdr, text="원본 이미지", bg="#ddd", width=22,
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)

        for fn in self.trans_files:
            self._make_row(fn)

    def _make_row(self, trans_fn):
        T = self.THUMB
        row = tk.Frame(self.rows_frame, bg="white", relief="ridge",
                       borderwidth=1, pady=4)
        row.pack(fill="x", padx=4, pady=3)

        # 번역본 썸네일
        trans_path = os.path.join(self.trans_dir, trans_fn)
        pil = _load_pil(trans_path, T)
        tk_img = _make_thumb_tk(pil, T) if pil else None

        left = tk.Frame(row, bg="white", width=T + 20, height=T + 30)
        left.pack(side="left", padx=8)
        left.pack_propagate(False)

        if tk_img:
            self._tk_refs.append(tk_img)
            tk.Label(left, image=tk_img, bg="white").place(x=0, y=0, width=T + 20, height=T + 4)
        else:
            tk.Label(left, text="[로드 실패]", bg="#eee").place(x=0, y=0, width=T + 20, height=T + 4)

        short_fn = trans_fn[:20] + "..." if len(trans_fn) > 24 else trans_fn
        tk.Label(left, text=short_fn, bg="white",
                 font=("Arial", 7), wraplength=T + 16).place(x=0, y=T + 6, width=T + 20, height=22)

        # 화살표
        tk.Label(row, text="→", bg="white",
                 font=("Arial", 16, "bold"), width=3).pack(side="left")

        # 원본 슬롯
        right = tk.Frame(row, bg="white", width=T + 20, height=T + 30)
        right.pack(side="left", padx=4)
        right.pack_propagate(False)

        # 썸네일 레이블 (선택 전: 회색 박스)
        orig_thumb_lbl = tk.Label(right, text="선택 안 됨",
                                  bg="#cccccc", font=("Arial", 9))
        orig_thumb_lbl.place(x=0, y=0, width=T + 20, height=T + 4)
        orig_name_lbl = tk.Label(right, text="", bg="white",
                                 font=("Arial", 7), wraplength=T + 16)
        orig_name_lbl.place(x=0, y=T + 6, width=T + 20, height=22)

        # 현재 선택 반영 (매핑 불러오기 후 재구성 시)
        current = self.mapping.get(trans_fn)
        if current:
            self._update_orig_slot(right, orig_thumb_lbl, orig_name_lbl, current)

        # 원본 선택 버튼
        def _pick(tfn=trans_fn, r=right, tl=orig_thumb_lbl, nl=orig_name_lbl):
            picker = CcfoliaOriginalPickerDialog(self, self.src_dir, self.src_files)
            self.wait_window(picker)
            # CcfoliaOriginalPickerDialog가 bind_all로 마우스 휠을 가로채므로
        # 소멸 후 이 캔버스의 스크롤 바인딩을 복구해야 한다.
            self.canvas.bind_all(
                "<MouseWheel>",
                lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units")
            )
            if picker.selected_filename:
                self.mapping[tfn] = picker.selected_filename
                self._update_orig_slot(r, tl, nl, picker.selected_filename)

        tk.Button(row, text="원본 선택", command=_pick,
                  bg="#2196F3", fg="white", width=10).pack(side="left", padx=8)

    def _update_orig_slot(self, frame, thumb_lbl, name_lbl, orig_fn):
        """원본 슬롯 UI 업데이트."""
        T = self.THUMB
        path = os.path.join(self.src_dir, orig_fn)
        pil = _load_pil(path, T)
        tk_img = _make_thumb_tk(pil, T) if pil else None

        if tk_img:
            self._tk_refs.append(tk_img)
            thumb_lbl.config(image=tk_img, text="", bg="white")
            thumb_lbl.image = tk_img
        else:
            thumb_lbl.config(image="", text="[로드 실패]", bg="#eee")

        short = orig_fn[:8] + "..." + orig_fn[-8:] if len(orig_fn) > 20 else orig_fn
        name_lbl.config(text=short)

    def _on_ok(self):
        """원본이 지정된 쌍만 result_pairs에 담아 다이얼로그를 닫는다. 매핑이 없는 항목은 무시한다."""
        self.result_pairs = [
            (os.path.join(self.trans_dir, tfn), ofn)
            for tfn, ofn in self.mapping.items()
            if ofn is not None
        ]
        self.destroy()

    def _save_mapping(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="매핑 저장",
            defaultextension=".json",
            filetypes=self.MAPPING_FILE_TYPES
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.mapping, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("저장 완료", f"매핑 저장됨: {os.path.basename(path)}", parent=self)
        except Exception as e:
            messagebox.showerror("저장 실패", str(e), parent=self)

    def _load_mapping(self):
        """저장된 JSON 매핑 파일을 불러와 현재 번역본 파일 목록에 일치하는 항목만 적용한다."""
        path = filedialog.askopenfilename(
            parent=self,
            title="매핑 불러오기",
            filetypes=self.MAPPING_FILE_TYPES
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            # 현재 trans_files에 해당하는 항목만 적용 (다른 작업의 매핑이 혼입되지 않도록)
            for fn in self.trans_files:
                if fn in loaded and loaded[fn]:
                    self.mapping[fn] = loaded[fn]
            # UI 재구성
            self._populate()
            messagebox.showinfo("불러오기 완료",
                                f"매핑 적용됨: {os.path.basename(path)}", parent=self)
        except Exception as e:
            messagebox.showerror("불러오기 실패", str(e), parent=self)


class CcfoliaAutoConfirmDialog(tk.Toplevel):
    """모드 B: 파일명 자동 매칭 결과 확인 다이얼로그."""

    THUMB = 160

    def __init__(self, parent, src_dir, matched):
        """
        matched: {orig_filename: trans_path}  (파일명이 같은 쌍)
        """
        super().__init__(parent)
        self.title(f"자동 매칭 확인 — {len(matched)}쌍")
        self.geometry("820x620")
        self.resizable(True, True)

        self.src_dir = src_dir
        self.matched = matched      # {orig_fn: trans_path}
        self.check_vars = {}        # {orig_fn: BooleanVar}
        self.confirmed_pairs = []   # 최종: [(trans_path, orig_fn), ...]
        self._tk_refs = []

        self._build_ui()
        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        # 상단
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)
        tk.Label(top, text=f"파일명이 일치하는 이미지 {len(self.matched)}쌍을 확인하세요.",
                 font=("Arial", 10, "bold")).pack(side="left")
        tk.Button(top, text="모두 선택", command=self._select_all, width=10).pack(side="right", padx=4)
        tk.Button(top, text="모두 해제", command=self._deselect_all, width=10).pack(side="right", padx=4)

        # 스크롤 캔버스
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=2)

        self.canvas = tk.Canvas(frame, bg="#f5f5f5")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg="#f5f5f5")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._populate()

        # 하단
        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=8)
        tk.Button(btn_row, text="취소", command=self.destroy, width=10).pack(side="right", padx=4)
        tk.Button(btn_row, text="선택 항목 교체", command=self._on_ok,
                  bg="#4CAF50", fg="white", width=14).pack(side="right", padx=4)

    def _populate(self):
        T = self.THUMB
        # 헤더
        hdr = tk.Frame(self.inner, bg="#ddd")
        hdr.pack(fill="x", padx=4, pady=(0, 2))
        tk.Label(hdr, text="☑", bg="#ddd", width=3).pack(side="left")
        tk.Label(hdr, text="원본", bg="#ddd", width=20,
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)
        tk.Label(hdr, text="→ 번역본", bg="#ddd", width=20,
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)

        for orig_fn, trans_path in self.matched.items():
            row = tk.Frame(self.inner, bg="white", relief="ridge", borderwidth=1)
            row.pack(fill="x", padx=4, pady=3)

            # 체크박스
            var = tk.BooleanVar(value=True)
            self.check_vars[orig_fn] = var
            tk.Checkbutton(row, variable=var, bg="white").pack(side="left", padx=4)

            # 원본 썸네일
            orig_pil = _load_pil(os.path.join(self.src_dir, orig_fn), T)
            orig_tk = _make_thumb_tk(orig_pil, T) if orig_pil else None

            orig_frame = tk.Frame(row, bg="white", width=T + 20, height=T + 30)
            orig_frame.pack(side="left", padx=8)
            orig_frame.pack_propagate(False)
            if orig_tk:
                self._tk_refs.append(orig_tk)
                tk.Label(orig_frame, image=orig_tk, bg="white").place(
                    x=0, y=0, width=T + 20, height=T + 4)
            else:
                tk.Label(orig_frame, text="[로드 실패]", bg="#eee").place(
                    x=0, y=0, width=T + 20, height=T + 4)
            short = orig_fn[:8] + "..." + orig_fn[-8:] if len(orig_fn) > 20 else orig_fn
            tk.Label(orig_frame, text=short, bg="white",
                     font=("Arial", 7), wraplength=T + 16).place(
                x=0, y=T + 6, width=T + 20, height=22)

            tk.Label(row, text="→", bg="white", font=("Arial", 12), width=3).pack(side="left")

            # 번역본 썸네일
            trans_pil = _load_pil(trans_path, T)
            trans_tk = _make_thumb_tk(trans_pil, T) if trans_pil else None

            trans_frame = tk.Frame(row, bg="white", width=T + 20, height=T + 30)
            trans_frame.pack(side="left", padx=8)
            trans_frame.pack_propagate(False)
            if trans_tk:
                self._tk_refs.append(trans_tk)
                tk.Label(trans_frame, image=trans_tk, bg="white").place(
                    x=0, y=0, width=T + 20, height=T + 4)
            else:
                tk.Label(trans_frame, text="[로드 실패]", bg="#eee").place(
                    x=0, y=0, width=T + 20, height=T + 4)
            trans_name = os.path.basename(trans_path)
            short_t = trans_name[:20] + "..." if len(trans_name) > 24 else trans_name
            tk.Label(trans_frame, text=short_t, bg="white",
                     font=("Arial", 7), wraplength=T + 16).place(
                x=0, y=T + 6, width=T + 20, height=22)

    def _select_all(self):
        for v in self.check_vars.values():
            v.set(True)

    def _deselect_all(self):
        for v in self.check_vars.values():
            v.set(False)

    def _on_ok(self):
        self.confirmed_pairs = [
            (trans_path, orig_fn)
            for orig_fn, trans_path in self.matched.items()
            if self.check_vars.get(orig_fn, tk.BooleanVar(value=False)).get()
        ]
        self.destroy()
