"""
gui.py — Tkinter 기반 GUI 메인 파일: TRPGTranslatorApp 클래스와 진입점을 정의한다.

기능별 로직은 Mixin으로 분리되어 있다:
  translation_mixin.py — 번역 / 용어집 추출 메서드
  image_mixin.py       — PDF 이미지 추출 / 이미지 글자 제거 메서드
  correction_mixin.py  — 번역 교정(2차 수정) 메서드
  ccfolia_mixin.py     — 코코포리아 룸 이미지 교체 메서드
  dialogs.py           — 각종 모달 다이얼로그 클래스
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk, simpledialog
import webbrowser
import threading
import os
import sys
import queue
import re
import math
import shutil
import config
from config import save_settings, load_settings
from translator import configure_genai

from translation_mixin import TranslationMixin
from image_mixin import ImageMixin
from correction_mixin import CorrectionMixin
from ccfolia_mixin import CcfoliaMixin

# Pre-compiled regex patterns (kept for backward compatibility / potential local use)
_RE_COLOR_TAG_SPLIT = re.compile(r'(<c=#[0-9a-fA-F]{6}>.*?</c>|<b>.*?</b>)', re.DOTALL)
_RE_COLOR_TAG_STRIP = re.compile(r'<c=#[0-9a-fA-F]{6}>|</c>|<b>|</b>')
_RE_INVALID_FILENAME = re.compile(r'[\\/*?:"<>|]')


class TRPGTranslatorApp(TranslationMixin, ImageMixin, CorrectionMixin, CcfoliaMixin):
    """TRPG 번역 도구의 메인 애플리케이션 클래스. 각 Mixin에서 기능별 메서드를 상속한다."""

    def __init__(self, root):
        self.root = root
        self.root.title("Japanese TRPG/Murder Mystery Translator v0.7")
        self.root.geometry("800x650")  # Slightly taller for settings/credits

        # Set Window Icon
        try:
            # Helper for PyInstaller bundled paths
            def resource_path(relative_path):
                """ Get absolute path to resource, works for dev and for PyInstaller """
                try:
                    # PyInstaller creates a temp folder and stores path in _MEIPASS
                    base_path = sys._MEIPASS
                except Exception:
                    base_path = os.path.abspath(".")
                return os.path.join(base_path, relative_path)

            # Use image.png for high-res window icon
            icon_path = resource_path("image.png")

            if os.path.exists(icon_path):
                # Using PhotoImage allows PNG usage
                icon_img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(False, icon_img)
            else:
                # Fallback to CWD
                local_path = os.path.join(os.getcwd(), "image.png")
                if os.path.exists(local_path):
                    icon_img = tk.PhotoImage(file=local_path)
                    self.root.iconphoto(False, icon_img)

        except Exception as e:
            print(f"Failed to load icon: {e}")

        # Settings
        self.settings = load_settings()
        self.api_key_var = tk.StringVar(value=self.settings["api_key"])
        self.model_name_var = tk.StringVar(value=self.settings["model_name"])

        # Translation Vars
        self.text_dir = tk.StringVar(value=self.settings.get("last_text_dir", ""))
        self.image_dir = tk.StringVar(value=self.settings.get("last_image_dir", ""))
        self.output_dir = tk.StringVar(value=self.settings.get("last_output_dir", ""))
        self.trans_glossary_file = tk.StringVar(value=self.settings.get("last_trans_glossary", ""))

        # Correction Vars
        self.correct_input_dir = tk.StringVar()
        self.correct_output_dir = tk.StringVar()
        self.correct_glossary_file = tk.StringVar()

        self.refine_enabled = tk.BooleanVar(value=False)
        self.docx_output_enabled = tk.BooleanVar(value=False)
        self.docx_font_name = tk.StringVar(value=self.settings.get("docx_font_name", "바탕"))
        self.docx_remove_headers = tk.BooleanVar(value=False)
        self.auto_apply_glossary = tk.BooleanVar(value=True)
        self.resume_enabled = tk.BooleanVar(value=False)
        self.auto_open_output = tk.BooleanVar(value=self.settings.get("auto_open_output", False))
        self.save_log_enabled = tk.BooleanVar(value=self.settings.get("save_log_enabled", True))

        # Ccfolia Vars
        self.ccfolia_src_dir = tk.StringVar(value=self.settings.get("ccfolia_src_dir", ""))
        self.ccfolia_trans_dir = tk.StringVar(value=self.settings.get("ccfolia_trans_dir", ""))
        self.ccfolia_output_dir = tk.StringVar(value=self.settings.get("ccfolia_output_dir", ""))
        self.ccfolia_match_mode = tk.StringVar(value=self.settings.get("ccfolia_match_mode", "manual"))
        self.ccfolia_make_zip = tk.BooleanVar(value=self.settings.get("ccfolia_make_zip", True))
        self.ccfolia_api_match = tk.BooleanVar(value=self.settings.get("ccfolia_api_match", False))
        self.ccfolia_api_match_model = tk.StringVar(value=self.settings.get("ccfolia_api_match_model", "gemini-3.1-flash-lite-preview"))
        self.ccfolia_translate_memo = tk.BooleanVar(value=self.settings.get("ccfolia_translate_memo", False))
        self.ccfolia_glossary_file = tk.StringVar(value=self.settings.get("ccfolia_glossary_file", ""))

        # Image Cleaner Vars (v0.5)
        self.ic_api_key = tk.StringVar(value=self.settings.get("image_cleaner_api_key", ""))
        self.ic_model_name = tk.StringVar(value=self.settings.get("image_cleaner_model_name", "gemini-3-pro-image-preview"))
        self.ic_input_dir = tk.StringVar(value=self.settings.get("last_ic_input_dir", ""))
        self.ic_output_dir = tk.StringVar(value=self.settings.get("last_ic_output_dir", ""))
        self.ic_prompt = tk.StringVar(value=self.settings.get("image_cleaner_prompt", "캐릭터나 그림은 유지하고 글자만 자연스럽게 지워줘"))
        self.ic_alpha_enabled = tk.BooleanVar(value=self.settings.get("image_cleaner_alpha_enabled", True))

        # UI Element placeholders
        self.open_glossary_btn = None
        self.auto_apply_check = None
        self.last_extracted_glossary = ""

        self.msg_queue = queue.Queue()

        # Determine UI Font
        available_families = tkfont.families()

        # Robust search for NanumBarunGothic
        found_font = None
        for f in available_families:
            if "NanumBarunGothic" in f:
                found_font = f
                break

        if found_font:
            self.ui_font_family = found_font
        else:
            # Fallback to hardcoded if not found in list (might still work)
            self.ui_font_family = "NanumBarunGothic"

        self.create_widgets()

        # Start checking queue
        self.root.after(100, self.process_queue)

    def create_widgets(self):
        # 1. Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # --- Tab 1: 설정 (Settings) ---
        self.tab_settings = tk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="설정 (Settings)")

        # API & Model Settings
        sett_frame = tk.LabelFrame(self.tab_settings, text="API 및 모델 설정")
        sett_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(sett_frame, text="Gemini API Key:", width=15, anchor="w").grid(row=0, column=0, padx=5, pady=5)
        tk.Entry(sett_frame, textvariable=self.api_key_var, show="*", width=50).grid(row=0, column=1, padx=5, pady=5)

        tk.Label(sett_frame, text="Model Name:", width=15, anchor="w").grid(row=1, column=0, padx=5, pady=5)
        tk.Entry(sett_frame, textvariable=self.model_name_var, width=50).grid(row=1, column=1, padx=5, pady=5)

        tk.Button(sett_frame, text="설정 저장 (Save)", command=self.save_app_settings, bg="#FF9800", fg="white").grid(row=2, column=1, sticky="e", padx=5, pady=10)

        # User Manual Button
        btn_manual = tk.Button(sett_frame, text="사용 설명서\n(User Manual)", command=self.open_manual, bg="#607D8B", fg="white", height=3)
        btn_manual.grid(row=0, column=2, rowspan=2, padx=10, pady=5)

        # Prompt Settings Button
        tk.Button(sett_frame, text="프롬프트 설정 (Prompts)", command=self.open_prompt_editor, bg="#9C27B0", fg="white").grid(row=2, column=0, sticky="w", padx=5, pady=10)

        # Presets
        presets_lf = tk.LabelFrame(self.tab_settings, text="설정 프리셋 (Presets)")
        presets_lf.pack(fill="x", padx=10, pady=5)

        preset_row = tk.Frame(presets_lf)
        preset_row.pack(fill="x", padx=5, pady=6)

        tk.Label(preset_row, text="프리셋:", width=8, anchor="w").pack(side="left")
        self.preset_combo = ttk.Combobox(preset_row, width=24, state="readonly")
        self.preset_combo.pack(side="left", padx=5)
        self._refresh_preset_combo()

        tk.Button(preset_row, text="불러오기", command=self._load_preset,
            bg="#2196F3", fg="white", width=8).pack(side="left", padx=3)
        tk.Button(preset_row, text="현재 설정 저장", command=self._save_preset,
            bg="#FF9800", fg="white", width=12).pack(side="left", padx=3)
        tk.Button(preset_row, text="삭제", command=self._delete_preset,
            bg="#F44336", fg="white", width=6).pack(side="left", padx=3)

        # Version History
        hist_frame = tk.LabelFrame(self.tab_settings, text="버전 히스토리 (Version History)")
        hist_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.history_area = scrolledtext.ScrolledText(hist_frame, height=10)
        self.history_area.pack(fill="both", expand=True, padx=5, pady=5)
        self.history_area.insert(tk.END, self.get_version_history())
        self.history_area.config(state='disabled')  # Read-only

        # --- Tab 2: 번역 실행 (Run Translation) ---
        self.tab_translation = tk.Frame(self.notebook)
        self.notebook.add(self.tab_translation, text="1차 번역 (Translation)")

        # Config Frame in Tab 2
        config_frame = tk.LabelFrame(self.tab_translation, text="경로 및 옵션 설정")
        config_frame.pack(fill="x", padx=10, pady=5)

        # Text Directory
        self.create_dir_selector(config_frame, "텍스트/PDF 폴더:", self.text_dir, 0, is_file=False)
        # Image Directory
        self.create_dir_selector(config_frame, "이미지 폴더:", self.image_dir, 1, is_file=False)
        # Output Directory
        self.create_dir_selector(config_frame, "결과물 저장 폴더:", self.output_dir, 2, is_file=False)
        # Glossary File (Translation)
        self.create_dir_selector(config_frame, "단어 사전 파일 (.txt):", self.trans_glossary_file, 3, is_file=True)

        # Action Frame in Tab 2
        action_frame = tk.Frame(self.tab_translation)
        action_frame.pack(fill="x", padx=10, pady=5)

        # ── 번역 옵션 LabelFrame ──────────────────────────────────────
        options_lf = tk.LabelFrame(action_frame, text="번역 옵션", padx=10, pady=8)
        options_lf.pack(fill="x", pady=(0, 6))

        # Row 1: 2차 교열
        refine_check = tk.Checkbutton(options_lf,
            text="2차 교열 활성화  —  번역 후 더 자연스러운 한국어로 다듬기",
            variable=self.refine_enabled,
            font=(self.ui_font_family, 9))
        refine_check.pack(anchor="w", pady=(0, 4))

        ttk.Separator(options_lf, orient="horizontal").pack(fill="x", pady=(0, 6))

        # Row 2: DOCX 출력 + 폰트
        docx_row = tk.Frame(options_lf)
        docx_row.pack(anchor="w", fill="x")
        docx_check = tk.Checkbutton(docx_row,
            text="DOCX 출력  —  글씨 색상 / 볼드 복원",
            variable=self.docx_output_enabled,
            font=(self.ui_font_family, 9))
        docx_check.pack(side="left")
        tk.Label(docx_row, text="폰트:", fg="#555",
            font=(self.ui_font_family, 9)).pack(side="left", padx=(18, 3))
        ttk.Entry(docx_row, textvariable=self.docx_font_name, width=13).pack(side="left")
        tk.Label(docx_row, text="(맑은 고딕, 바탕 …)", fg="#999",
            font=(self.ui_font_family, 8)).pack(side="left", padx=5)

        # Row 3: 헤더 제거 (DOCX 하위 옵션, 들여쓰기)
        tk.Checkbutton(options_lf,
            text="페이지 헤더 제거  ([1페이지], [2~3페이지] 구분선 숨기기)",
            variable=self.docx_remove_headers,
            font=(self.ui_font_family, 9),
            fg="#444").pack(anchor="w", padx=(26, 0), pady=(5, 0))

        ttk.Separator(options_lf, orient="horizontal").pack(fill="x", pady=(8, 4))

        # Row 4: 번역 재개
        tk.Checkbutton(options_lf,
            text="이미 번역된 파일 건너뛰기  (이어서 번역 / Resume)",
            variable=self.resume_enabled,
            font=(self.ui_font_family, 9)).pack(anchor="w", pady=(0, 4))

        ttk.Separator(options_lf, orient="horizontal").pack(fill="x", pady=(0, 4))

        # Row 5: 완료 후 옵션
        completion_row = tk.Frame(options_lf)
        completion_row.pack(anchor="w", fill="x")
        tk.Label(completion_row, text="완료 후:",
            font=(self.ui_font_family, 9), fg="#555").pack(side="left", padx=(0, 8))
        tk.Checkbutton(completion_row,
            text="폴더 자동 열기",
            variable=self.auto_open_output,
            font=(self.ui_font_family, 9)).pack(side="left", padx=(0, 16))
        tk.Checkbutton(completion_row,
            text="로그 파일 저장",
            variable=self.save_log_enabled,
            font=(self.ui_font_family, 9)).pack(side="left")

        # ── 버튼 (grid 3열) ──────────────────────────────────────────
        btn_frame = tk.Frame(action_frame)
        btn_frame.pack(fill="x", pady=(0, 5))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=2)

        self.extract_images_btn = tk.Button(btn_frame,
            text="PDF 이미지 추출",
            command=self.start_extract_pdf_images,
            bg="#795548", fg="white",
            font=(self.ui_font_family, 10, "bold"), relief="flat")
        self.extract_images_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=7)

        self.glossary_btn = tk.Button(btn_frame,
            text="고유명사 자동 추출",
            command=self.start_glossary_extraction,
            bg="#3F51B5", fg="white",
            font=(self.ui_font_family, 10, "bold"), relief="flat")
        self.glossary_btn.grid(row=0, column=1, sticky="ew", padx=(0, 4), ipady=7)

        self.start_btn = tk.Button(btn_frame,
            text="번역 시작",
            command=self.start_translation,
            bg="#4CAF50", fg="white",
            font=(self.ui_font_family, 12, "bold"), relief="flat")
        self.start_btn.grid(row=0, column=2, sticky="ew", ipady=7)

        self.preview_btn = tk.Button(btn_frame,
            text="미리보기 (첫 3청크)",
            command=self.start_quick_preview,
            bg="#009688", fg="white",
            font=(self.ui_font_family, 9), relief="flat")
        self.preview_btn.grid(row=1, column=2, sticky="ew", ipady=3, pady=(2, 0))

        # ── 단어 사전 옵션 (컴팩트 바) ───────────────────────────────
        glossary_opt_frame = tk.Frame(action_frame, bg="#F2F2F2", relief="groove", bd=1)
        glossary_opt_frame.pack(fill="x", pady=(0, 6))

        self.open_glossary_btn = tk.Button(glossary_opt_frame,
            text="추출된 단어 사전 열기 (auto_glossary.txt)",
            command=self.open_extracted_glossary,
            state="disabled",
            bg="#F2F2F2", relief="flat",
            font=(self.ui_font_family, 9), fg="#555")
        self.open_glossary_btn.pack(side="left", padx=8, pady=4)

        tk.Frame(glossary_opt_frame, width=1, bg="#CCCCCC").pack(side="left", fill="y", pady=4)

        self.auto_apply_check = tk.Checkbutton(glossary_opt_frame,
            text="추출 성공 시 단어 사전에 자동 적용",
            variable=self.auto_apply_glossary,
            bg="#F2F2F2",
            font=(self.ui_font_family, 9))
        self.auto_apply_check.pack(side="left", padx=8, pady=4)

        tk.Frame(glossary_opt_frame, width=1, bg="#CCCCCC").pack(side="left", fill="y", pady=4)

        tk.Button(glossary_opt_frame,
            text="✏ 사전 편집",
            command=self.open_glossary_editor,
            bg="#F2F2F2", relief="flat",
            font=(self.ui_font_family, 9), fg="#333").pack(side="left", padx=8, pady=4)

        # ── 진행 상황 ────────────────────────────────────────────────
        self.progress = ttk.Progressbar(action_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=(2, 2))

        self.status_label = tk.Label(action_frame, text="준비됨",
            fg="#555", font=(self.ui_font_family, 9))
        self.status_label.pack(anchor="w", pady=(2, 0))

        # --- Tab 3: 번역 교정 (Post-Correction) ---
        self.tab_correction = tk.Frame(self.notebook)
        self.notebook.add(self.tab_correction, text="2차 수정 (Correction)")

        correction_frame = tk.LabelFrame(self.tab_correction, text="기존 번역물 수정 (단어 일괄 교체)")
        correction_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(correction_frame, text="* 단어 사전 파일(.txt)을 기반으로 HTML 파일을 일괄 수정합니다.", fg="blue").grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        self.create_dir_selector(correction_frame, "원본 HTML 폴더:", self.correct_input_dir, 1, is_file=False)
        self.create_dir_selector(correction_frame, "수정본 저장 폴더:", self.correct_output_dir, 2, is_file=False)
        # Glossary File (Correction)
        self.create_dir_selector(correction_frame, "단어 사전 파일 (.txt):", self.correct_glossary_file, 3, is_file=True)

        btn_apply = tk.Button(correction_frame, text="수정 적용 (HTML)", command=self.apply_corrections, bg="#2196F3", fg="white", font=(self.ui_font_family, 11, "bold"))
        btn_apply.grid(row=4, column=1, pady=15, sticky="ew")

        # --- Tab 4: 이미지 글자 제거 (beta) ---
        self.tab_cleaner = tk.Frame(self.notebook)
        self.notebook.add(self.tab_cleaner, text="이미지 글자 제거 (beta)")

        cleaner_container = tk.LabelFrame(self.tab_cleaner, text="이미지 글자 제거 및 배경 복구 (Image Cleaner)")
        cleaner_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Cleaner API Settings
        ic_api_frame = tk.LabelFrame(cleaner_container, text="이미지 클리너 전용 설정 (Image Cleaner API Settings)")
        ic_api_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(ic_api_frame, text="Gemini API Key:", width=15, anchor="w").grid(row=0, column=0, padx=5, pady=5)
        tk.Entry(ic_api_frame, textvariable=self.ic_api_key, show="*", width=50).grid(row=0, column=1, padx=5, pady=5)

        tk.Label(ic_api_frame, text="Model Name:", width=15, anchor="w").grid(row=1, column=0, padx=5, pady=5)
        tk.Entry(ic_api_frame, textvariable=self.ic_model_name, width=50).grid(row=1, column=1, padx=5, pady=5)

        # Cleaner Path Settings
        ic_path_frame = tk.Frame(cleaner_container)
        ic_path_frame.pack(fill="x", padx=10, pady=5)

        self.create_dir_selector(ic_path_frame, "입력 폴더 (하위 포함):", self.ic_input_dir, 0, is_file=False)
        self.create_dir_selector(ic_path_frame, "결과 저장 폴더:", self.ic_output_dir, 1, is_file=False)

        # Prompt & Options
        ic_opt_frame = tk.Frame(cleaner_container)
        ic_opt_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(ic_opt_frame, text="지시 사항 (Prompt):", width=20, anchor="w").grid(row=0, column=0, padx=5, pady=5)
        tk.Entry(ic_opt_frame, textvariable=self.ic_prompt, width=65).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(ic_opt_frame, text="(예: 캐릭터나 그림은 유지하고 글자만 자연스럽게 지워줘)", fg="gray", font=(self.ui_font_family, 8)).grid(row=1, column=1, sticky="w", padx=5)

        tk.Checkbutton(ic_opt_frame, text="Alpha 채널(투명도) 유지", variable=self.ic_alpha_enabled).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.ic_status_label = tk.Label(ic_opt_frame, text="이미지 클리너 준비됨")
        self.ic_status_label.grid(row=2, column=1, sticky="e", padx=5)

        # Buttons
        ic_btn_frame = tk.Frame(cleaner_container)
        ic_btn_frame.pack(fill="x", pady=20)

        tk.Button(ic_btn_frame, text="한 장 미리보기", command=self.preview_image_clean, bg="#607D8B", fg="white", font=(self.ui_font_family, 10, "bold"), width=15).pack(side="left", padx=(150, 10))
        self.ic_start_btn = tk.Button(ic_btn_frame, text="이미지 글자 제거 시작 (Batch)", command=self.start_batch_clean, bg="#4CAF50", fg="white", font=(self.ui_font_family, 11, "bold"), width=30)
        self.ic_start_btn.pack(side="left", padx=10)

        # --- Tab 5: 코코포리아 ---
        self.tab_ccfolia = tk.Frame(self.notebook)
        self.notebook.add(self.tab_ccfolia, text="코코포리아 룸 셋팅")
        self.setup_ccfolia_tab(self.tab_ccfolia)

        # --- Global: Log Area (Bottom of Root) ---
        log_frame = tk.LabelFrame(self.root, text="로그 및 미리보기 (Log & Preview)")
        log_frame.pack(side="bottom", fill="both", expand=True, padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=10)
        self.log_area.pack(fill="both", expand=True)

        # Footer Credit
        footer_font_family = "Arial"
        available_fonts = set(tkfont.families(self.root))

        target_fonts = ["NanumBarunGothic", "NanumBarunGothic Regular", "나눔바른고딕", "NanumBarunGothicBold"]
        for f in target_fonts:
            if f in available_fonts:
                footer_font_family = f
                break

        footer_label = tk.Label(self.root, text="제작자 : 포하", fg="gray", font=(footer_font_family, 9))
        footer_label.pack(side="bottom", anchor="e", padx=10, pady=5)

    def get_version_history(self):
        return """
v0.7 (Current):
- 코코포리아 이미지 교체: ccfolia 룸 폴더의 이미지를 번역본으로 교체 (수동 매핑 / 파일명 자동 매칭)
- 매핑 저장/불러오기: 이미지 매핑 설정을 JSON 파일로 저장하여 재사용 가능
- 자동 매칭 확인 다이얼로그: 매칭된 이미지 쌍을 시각적으로 확인 후 교체 진행
- __data.json 해시 자동 치환: 64자 SHA-256 해시명 기반으로 모든 이미지 참조를 일괄 업데이트
- ZIP 출력 옵션: 교체 완료 후 코코포리아 업로드용 ZIP 자동 생성

v0.6:
- 번역 재개 (Resume): 이미 번역된 파일 건너뛰기 옵션 추가
- 1페이지 미리번역: 첫 3청크를 빠르게 번역해 팝업 창으로 결과 확인
- 용어집 내장 편집기: 단어 사전 파일을 GUI에서 바로 편집
- 출력 폴더 자동 열기: 번역 완료 후 결과 폴더를 자동으로 탐색기에서 열기
- 설정 프리셋: 자주 쓰는 모델/폰트/옵션 조합을 이름으로 저장·불러오기
- 번역 통계: 완료 시 파일/청크 수 및 소요 시간 표시
- PDF 스캔본 감지: 텍스트 레이어 없는 페이지 자동 감지 및 경고
- 로그 파일 저장: 번역 완료 시 로그를 자동으로 텍스트 파일로 저장

v0.5:
- 이미지 글자 제거 (beta) 기능 추가: AI를 이용해 이미지 배경 손상 없이 글씨만 자연스럽게 제거
- 이미지 미리보기 다이얼로그 추가: 원본과 결과물 실시간 비교 가능
- 일괄 처리 지원: 하위 폴더 구조를 유지하며 여러 장의 이미지 동시 세척
- 알파 채널(투명도) 유지 옵션 추가
- GUI 안정성 개선 및 버그 수정

v0.4:
- DOCX 출력 지원: 번역된 텍스트를 워드 문서(.docx)로 자동 생성
- 원본 서식 복원: DOCX 출력 시 원본의 글씨 색상 및 폰트 최대한 유지
- 고유명사 자동 추출 (사전 생성): 시나리오 내 주요 인명, 지명 사전 자동 생성 기능
- 폴더 구조 보존: 입력 폴더의 서브 폴더 구조를 출력 폴더에 동일하게 재현

v0.3:
- PDF 이미지 선택 기능 추가: 필요한 페이지만 골라서 번역 가능
"""

    def open_extracted_glossary(self):
        """Opens the last extracted glossary text file."""
        if hasattr(self, 'last_extracted_glossary') and self.last_extracted_glossary and os.path.exists(self.last_extracted_glossary):
            import subprocess
            if sys.platform == "win32":
                os.startfile(self.last_extracted_glossary)
            elif sys.platform == "darwin":
                subprocess.call(["open", self.last_extracted_glossary])
            else:
                subprocess.call(["xdg-open", self.last_extracted_glossary])
        else:
            messagebox.showwarning("오류", "열 수 있는 자동 추출 사전 파일이 없습니다.")

    def open_manual(self):
        """Opens the User Manual HTML file in default browser."""
        try:
            manual_name = "manual.html"
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))

            manual_path = os.path.join(base_path, manual_name)

            if os.path.exists(manual_path):
                webbrowser.open(f"file://{manual_path}")
            else:
                # Fallback to CWD
                local_path = os.path.join(os.getcwd(), manual_name)
                if os.path.exists(local_path):
                    webbrowser.open(f"file://{local_path}")
                else:
                    messagebox.showerror("Error", "매뉴얼 파일을 찾을 수 없습니다.")
        except Exception as e:
            messagebox.showerror("Error", f"매뉴얼 열기 실패: {e}")

    def save_app_settings(self):
        """API 키와 모델명을 검증한 뒤 settings.json에 저장하고 Gemini 클라이언트를 재설정한다."""
        ak = self.api_key_var.get().strip()
        mn = self.model_name_var.get().strip()

        # 저장 전 API 연결 검증 (실제 토큰을 소비하지 않는 count_tokens 호출)
        from translator import validate_api_connection

        valid, message = validate_api_connection(ak, mn)
        if not valid:
            messagebox.showerror("Validation Error", message)

            if not messagebox.askyesno("Save Anyway?", "API 검증에 실패했습니다. 그래도 저장을 진행하시겠습니까?"):
                return

        if save_settings(
            ak, mn,
            image_cleaner_api_key=self.ic_api_key.get().strip(),
            image_cleaner_model_name=self.ic_model_name.get().strip(),
            image_cleaner_prompt=self.ic_prompt.get(),
            image_cleaner_alpha_enabled=self.ic_alpha_enabled.get(),
            auto_open_output=self.auto_open_output.get(),
            save_log_enabled=self.save_log_enabled.get(),
        ):
            # Re-configure runtime
            configure_genai(
                ak, mn,
                cleaner_api_key=self.ic_api_key.get().strip(),
                cleaner_model_name=self.ic_model_name.get().strip()
            )
            messagebox.showinfo("Success", "설정이 저장되었습니다.")
            self.log("Settings saved.")
        else:
            messagebox.showerror("Error", "설정 저장 실패.")

    def create_dir_selector(self, parent, label_text, var, row, is_file=False):
        """레이블 + 입력 필드 + 폴더/파일 선택 버튼으로 구성된 경로 선택 위젯 행을 생성한다."""
        tk.Label(parent, text=label_text, width=20, anchor="w").grid(row=row, column=0, padx=5, pady=5)
        entry = tk.Entry(parent, textvariable=var, width=50)
        entry.grid(row=row, column=1, padx=5, pady=5)
        cmd = lambda: self.browse_file(var) if is_file else self.browse_dir(var)
        btn_text = "파일 선택" if is_file else "폴더 선택"
        tk.Button(parent, text=btn_text, command=cmd).grid(row=row, column=2, padx=5, pady=5)

    def browse_dir(self, var):
        directory = filedialog.askdirectory()
        if directory:
            var.set(directory)

    def browse_file(self, var):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            var.set(filename)

    def log(self, message):
        """백그라운드 스레드에서 호출 가능한 로그 메서드. 메시지를 큐에 넣어 메인 스레드에서 처리한다."""
        self.msg_queue.put(("log", message))

    def update_progress(self, current, total, status_text):
        """프로그레스바와 상태 레이블을 갱신하는 메시지를 큐에 넣는다."""
        self.msg_queue.put(("progress", (current, total, status_text)))

    def process_queue(self):
        """100ms마다 호출되어 백그라운드 스레드가 쌓아둔 UI 업데이트 메시지를 처리한다.

        Tkinter는 메인 스레드에서만 UI를 조작할 수 있으므로, 백그라운드 작업의 결과는
        모두 msg_queue를 통해 이 메서드로 전달된다.
        """
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "log":
                    self.log_area.config(state='normal')
                    self.log_area.insert(tk.END, data + "\n")
                    self.log_area.see(tk.END)
                    self.log_area.config(state='disabled')
                elif msg_type == "progress":
                    current, total, status_text = data
                    self.progress["maximum"] = total
                    self.progress["value"] = current
                    self.status_label.config(text=status_text)
                elif msg_type == "done":
                    if hasattr(self, 'start_btn') and self.start_btn:
                        self.start_btn.config(state='normal')
                    if hasattr(self, 'glossary_btn') and self.glossary_btn:
                        self.glossary_btn.config(state='normal')
                    if hasattr(self, 'extract_images_btn') and self.extract_images_btn:
                        self.extract_images_btn.config(state='normal')
                    # Build completion message with stats
                    stats = data
                    if isinstance(stats, dict):
                        elapsed = stats.get("elapsed", 0)
                        m, s = divmod(int(elapsed), 60)
                        msg = (f"번역 완료!\n\n"
                               f"파일 {stats.get('files', 0)}개 · 청크 {stats.get('chunks', 0)}개\n"
                               f"소요: {m}분 {s}초")
                        if stats.get("errors", 0):
                            msg += f"\n⚠ 오류: {stats['errors']}개 (로그 확인)"
                    else:
                        msg = "번역 완료!"
                    # Auto-open output folder
                    try:
                        if hasattr(self, 'auto_open_output') and self.auto_open_output.get():
                            out_path = self.output_dir.get()
                            if out_path and os.path.exists(out_path):
                                os.startfile(out_path)
                    except Exception:
                        pass
                    # Save log file
                    try:
                        if hasattr(self, 'save_log_enabled') and self.save_log_enabled.get():
                            import datetime
                            log_content = self.log_area.get("1.0", tk.END)
                            out_path = self.output_dir.get()
                            if out_path and os.path.exists(out_path):
                                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                log_path = os.path.join(out_path, f"translation_log_{ts}.txt")
                                with open(log_path, "w", encoding="utf-8") as lf:
                                    lf.write(log_content)
                                self.log_area.config(state='normal')
                                self.log_area.insert(tk.END, f"로그 저장됨: {os.path.basename(log_path)}\n")
                                self.log_area.config(state='disabled')
                    except Exception:
                        pass
                    messagebox.showinfo("완료", msg)
                elif msg_type == "preview_result":
                    fname, result_text = data
                    popup = tk.Toplevel(self.root)
                    popup.title(f"미리보기 결과 — {fname}")
                    popup.geometry("700x500")
                    popup.transient(self.root)
                    txt = scrolledtext.ScrolledText(popup, wrap="word",
                        font=(self.ui_font_family, 10))
                    txt.pack(fill="both", expand=True, padx=10, pady=10)
                    txt.insert(tk.END, result_text)
                    txt.config(state='disabled')
                    tk.Button(popup, text="닫기", command=popup.destroy,
                        width=15, height=2).pack(pady=5)
                elif msg_type == "done_glossary":
                    if hasattr(self, 'start_btn') and self.start_btn:
                        self.start_btn.config(state='normal')
                    if hasattr(self, 'glossary_btn') and self.glossary_btn:
                        self.glossary_btn.config(state='normal')
                    if hasattr(self, 'extract_images_btn') and self.extract_images_btn:
                        self.extract_images_btn.config(state='normal')
                elif msg_type == "glossary_success":
                    # data is out_file path
                    if hasattr(self, 'open_glossary_btn') and self.open_glossary_btn:
                        self.open_glossary_btn.config(state='normal')
                        self.last_extracted_glossary = data

                    if self.auto_apply_glossary.get():
                        self.trans_glossary_file.set(data)
                        messagebox.showinfo("사전 추출 완료", f"고유명사 추출이 완료되었습니다!\n저장 경로: {data}\n\n'단어 사전 파일' 입력란에 자동으로 적용되었습니다.")
                    else:
                        messagebox.showinfo("사전 추출 완료", f"고유명사 추출이 완료되었습니다!\n저장 경로: {data}")
                elif msg_type == "error":
                    if hasattr(self, 'start_btn') and self.start_btn:
                        self.start_btn.config(state='normal')
                    if hasattr(self, 'glossary_btn') and self.glossary_btn:
                        self.glossary_btn.config(state='normal')
                    if hasattr(self, 'ic_start_btn') and self.ic_start_btn:
                        self.ic_start_btn.config(state='normal')
                    messagebox.showerror("Error", data)
                elif msg_type == "ic_done":
                    if hasattr(self, 'ic_start_btn') and self.ic_start_btn:
                        self.ic_start_btn.config(state='normal')
                    self.ic_status_label.config(text="이미지 클리닝 완료")
                self.msg_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def load_glossary_from_file(self, filepath):
        """'원어:한국어' 형식의 .txt 용어집 파일을 파싱해 dict로 반환한다."""
        glossary = {}
        if not filepath or not os.path.exists(filepath):
            return glossary

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        glossary[key.strip()] = value.strip()
            self.log(f"Loaded glossary from {os.path.basename(filepath)}: {len(glossary)} terms.")
        except Exception as e:
            self.log(f"Error loading glossary: {str(e)}")
            messagebox.showwarning("Warning", f"Failed to load glossary file: {str(e)}")

        return glossary

    def open_prompt_editor(self):
        """번역 규칙 편집 및 Gemini API 기반 시스템 프롬프트 자동 최적화 창을 연다."""
        editor = tk.Toplevel(self.root)
        editor.title("프롬프트 설정 (Prompt Settings)")
        editor.geometry("700x800")

        # 1. Rules Editor
        tk.Label(editor, text="번역 규칙 (Translation Rules) - 수정 가능", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        tk.Label(editor, text="작품의 분위기, 어조, 주의사항 등을 자유롭게 적어주세요.").pack(anchor="w", padx=10)

        rules_text = scrolledtext.ScrolledText(editor, height=10)
        rules_text.pack(fill="x", padx=10, pady=5)
        rules_text.insert(tk.END, config.TRANSLATION_RULES)

        # 2. Optimization Control
        opt_frame = tk.LabelFrame(editor, text="자동 최적화 (Auto-Optimize)")
        opt_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(opt_frame, text="위 규칙을 기반으로 시스템 프롬프트를 자동으로 다시 작성합니다.\n(Gemini API 사용)").pack(anchor="w", padx=10, pady=5)

        btn_optimize = tk.Button(opt_frame, text="프롬프트 자동 생성/최적화 (Generate Prompts)", bg="#2196F3", fg="white")
        btn_optimize.pack(fill="x", padx=10, pady=10)

        # 3. Preview (Read-only)
        preview_frame = tk.LabelFrame(editor, text="생성된 프롬프트 미리보기 (Preview)")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        tk.Label(preview_frame, text="System Prompt (Translation):").pack(anchor="w", padx=5)
        sys_preview = scrolledtext.ScrolledText(preview_frame, height=8, state='disabled')
        sys_preview.pack(fill="x", padx=5, pady=2)

        tk.Label(preview_frame, text="Refine Prompt (Correction):").pack(anchor="w", padx=5)
        ref_preview = scrolledtext.ScrolledText(preview_frame, height=8, state='disabled')
        ref_preview.pack(fill="x", padx=5, pady=2)

        # Load current prompts into preview
        self._update_preview(sys_preview, config.SYSTEM_PROMPT)
        self._update_preview(ref_preview, config.REFINE_SYSTEM_PROMPT)

        # 4. Actions
        btn_frame = tk.Frame(editor)
        btn_frame.pack(fill="x", padx=10, pady=10)

        btn_save = tk.Button(btn_frame, text="적용 및 저장 (Apply & Save)", bg="#4CAF50", fg="white", height=2)
        btn_save.pack(fill="x")

        # Logic Helpers
        current_generated = {
            "system_prompt": config.SYSTEM_PROMPT,
            "refine_system_prompt": config.REFINE_SYSTEM_PROMPT
        }

        def run_optimization():
            rules = rules_text.get(1.0, tk.END).strip()
            if not rules:
                messagebox.showwarning("Warning", "규칙을 입력해주세요.")
                return

            api_key = self.api_key_var.get().strip()
            model_name = self.model_name_var.get().strip()

            if not api_key:
                messagebox.showerror("Error", "메인 창에서 API Key를 먼저 설정해주세요.")
                editor.lift()
                return

            btn_optimize.config(state='disabled', text="생성 중... (Generating...)")
            editor.update()

            # UI 블로킹 방지를 위해 별도 스레드에서 API 호출
            def _thread_target():
                from translator import optimize_prompts
                success, sys_p, ref_p = optimize_prompts(rules, api_key, model_name)

                def _ui_update():
                    if success:
                        current_generated["system_prompt"] = sys_p
                        current_generated["refine_system_prompt"] = ref_p
                        self._update_preview(sys_preview, sys_p)
                        self._update_preview(ref_preview, ref_p)
                        messagebox.showinfo("Success", "프롬프트 최적화 완료! '저장' 버튼을 눌러 적용하세요.")
                    else:
                        messagebox.showerror("Error", f"최적화 실패: {sys_p}")

                    btn_optimize.config(state='normal', text="프롬프트 자동 생성/최적화 (Generate Prompts)")

                self.root.after(0, _ui_update)

            threading.Thread(target=_thread_target, daemon=True).start()

        def save_and_close():
            rules = rules_text.get(1.0, tk.END).strip()
            sys_p = current_generated["system_prompt"]
            ref_p = current_generated["refine_system_prompt"]

            if config.save_prompts(rules, sys_p, ref_p):
                # Update global config module
                config.TRANSLATION_RULES = rules
                config.SYSTEM_PROMPT = sys_p
                config.REFINE_SYSTEM_PROMPT = ref_p

                # Re-configure GenAI with new prompts
                api_key = self.api_key_var.get().strip()
                model_name = self.model_name_var.get().strip()
                configure_genai(api_key, model_name)

                messagebox.showinfo("Saved", "설정이 저장되고 적용되었습니다.")
                editor.destroy()
            else:
                messagebox.showerror("Error", "설정 저장 실패.")

        btn_optimize.config(command=run_optimization)
        btn_save.config(command=save_and_close)

    def _update_preview(self, widget, text):
        widget.config(state='normal')
        widget.delete(1.0, tk.END)
        widget.insert(tk.END, text)
        widget.config(state='disabled')

    # ── 용어집 편집기 ─────────────────────────────────────────────────────

    def open_glossary_editor(self):
        """현재 단어 사전 파일을 GUI 편집기로 연다."""
        from dialogs import GlossaryEditorDialog
        filepath = self.trans_glossary_file.get().strip()
        if not filepath:
            messagebox.showwarning("사전 파일 없음",
                "단어 사전 파일 경로를 먼저 입력해주세요.\n"
                "(또는 파일 선택 버튼으로 .txt 파일을 선택하세요.)")
            return
        GlossaryEditorDialog(self.root, filepath)

    # ── 설정 프리셋 ───────────────────────────────────────────────────────

    def _refresh_preset_combo(self):
        """settings.json 에서 프리셋 목록을 읽어 Combobox를 갱신한다."""
        presets = config.load_presets()
        names = [p.get("name", "") for p in presets]
        self.preset_combo["values"] = names
        if names:
            self.preset_combo.current(0)

    def _load_preset(self):
        """선택된 프리셋을 불러와 UI 값에 적용한다."""
        name = self.preset_combo.get()
        if not name:
            return
        presets = config.load_presets()
        preset = next((p for p in presets if p.get("name") == name), None)
        if not preset:
            return
        if "model_name" in preset:
            self.model_name_var.set(preset["model_name"])
        if "docx_font_name" in preset:
            self.docx_font_name.set(preset["docx_font_name"])
        if "refine_enabled" in preset:
            self.refine_enabled.set(preset["refine_enabled"])
        if "resume_enabled" in preset:
            self.resume_enabled.set(preset["resume_enabled"])
        messagebox.showinfo("프리셋 로드", f"'{name}' 프리셋을 불러왔습니다.")

    def _save_preset(self):
        """현재 설정을 이름을 지정해 프리셋으로 저장한다."""
        name = self.preset_combo.get().strip()
        if not name:
            name = simpledialog.askstring("프리셋 이름", "저장할 프리셋 이름을 입력하세요:", parent=self.root)
            if not name:
                return
        preset = {
            "name": name,
            "model_name": self.model_name_var.get().strip(),
            "docx_font_name": self.docx_font_name.get().strip(),
            "refine_enabled": self.refine_enabled.get(),
            "resume_enabled": self.resume_enabled.get(),
        }
        if config.save_preset(preset):
            self._refresh_preset_combo()
            # Select the just-saved preset
            values = list(self.preset_combo["values"])
            if name in values:
                self.preset_combo.current(values.index(name))
            messagebox.showinfo("저장 완료", f"프리셋 '{name}'이 저장되었습니다.")
        else:
            messagebox.showerror("저장 실패", "프리셋 저장에 실패했습니다.")

    def _delete_preset(self):
        """선택된 프리셋을 삭제한다."""
        name = self.preset_combo.get()
        if not name:
            return
        if not messagebox.askyesno("삭제 확인", f"프리셋 '{name}'을 삭제하시겠습니까?"):
            return
        if config.delete_preset(name):
            self._refresh_preset_combo()
        else:
            messagebox.showerror("삭제 실패", "프리셋 삭제에 실패했습니다.")


def load_custom_font():
    """NanumBarunGothic.ttf를 시스템에 임시 로드한다 (설치 불필요, FR_PRIVATE 플래그).

    PyInstaller 번들 실행 파일과 개발 환경 양쪽에서 폰트 경로를 탐색한다.
    """
    try:
        import ctypes
        import os
        import sys

        font_names = ["NanumBarunGothic.ttf"]

        # Determine search paths
        search_roots = [os.getcwd()]

        # If running as executable
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            search_roots.append(exe_dir)
            # Parent directory of exe (useful if exe is in dist/ and font is in root/)
            search_roots.append(os.path.dirname(exe_dir))
        else:
            search_roots.append(os.path.dirname(os.path.abspath(__file__)))

        paths_to_check = []
        for root in search_roots:
            paths_to_check.append(os.path.join(root, "font"))
            paths_to_check.append(root)

        font_path = None
        for path in paths_to_check:
            for fname in font_names:
                p = os.path.join(path, fname)
                if os.path.exists(p):
                    font_path = p
                    break
            if font_path:
                break

        if not font_path:
            print("Font file not found locally.")
            return False

        # 0x10 = FR_PRIVATE: 현재 프로세스에서만 사용, 시스템 폰트 목록에 등록하지 않음
        result = ctypes.windll.gdi32.AddFontResourceExW(
            font_path,
            0x10,
            0
        )
        if result > 0:
            print(f"Loaded custom font: {font_path}")
            return True
        else:
            print(f"Failed to load custom font: {font_path}")
            return False

    except Exception as e:
        print(f"Error loading custom font: {e}")
        return False


if __name__ == "__main__":
    try:
        root = tk.Tk()

        # Try to load custom font
        if load_custom_font():
            # Apply to global style
            default_font = ("NanumBarunGothic", 10)
            root.option_add("*Font", default_font)

            # Update Ttk styles
            style = ttk.Style()
            style.configure(".", font=default_font)

        app = TRPGTranslatorApp(root)
        root.mainloop()
    except Exception as e:
        # If GUI fails to launch (e.g. no display), print error
        print(f"Failed to launch GUI: {e}")
