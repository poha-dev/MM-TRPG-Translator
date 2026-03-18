"""
ccfolia_mixin.py — 코코포리아(CoCoFolio) 룸 ZIP의 이미지를 번역본으로 교체하는 Mixin 클래스.

코코포리아는 이미지를 SHA-256 해시명으로 저장하고 __data.json에서 참조한다.
이 Mixin은 번역된 이미지의 해시를 계산해 __data.json의 참조를 일괄 치환한 뒤
업로드용 ZIP을 생성한다. 이미지 매핑 방식은 수동(GUI)과 파일명 자동 매칭 두 가지를 지원한다.
"""
import hashlib
import shutil
import zipfile
import os
import threading
import json

from PIL import Image


def _sha256_of_file(filepath: str) -> str:
    """파일 전체를 64KB 청크로 읽어 SHA-256 16진수 다이제스트를 반환한다.

    코코포리아는 이미지 파일명으로 SHA-256 해시를 사용하므로,
    교체할 번역 이미지의 새 파일명을 계산하는 데 사용한다.
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_thumbnails(folder: str, filenames: list, size: int = 120):
    """파일명 리스트에서 PIL 썸네일 dict {filename: PIL.Image} 반환."""
    thumbs = {}
    for fn in filenames:
        path = os.path.join(folder, fn)
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((size, size))
            thumbs[fn] = img
        except Exception:
            thumbs[fn] = None
    return thumbs


class CcfoliaMixin:
    """코코포리아 룸 이미지 교체 기능을 제공하는 Mixin."""

    # ── 탭 GUI 구성 ────────────────────────────────────────────────────

    def setup_ccfolia_tab(self, parent):
        """'코코포리아 룸 셋팅' 탭의 UI 위젯을 생성한다."""
        import tkinter as tk
        from tkinter import ttk

        # 경로 설정 프레임
        path_lf = tk.LabelFrame(parent, text="경로 설정")
        path_lf.pack(fill="x", padx=10, pady=10)

        self.create_dir_selector(path_lf, "원본 폴더:", self.ccfolia_src_dir, 0)
        self.create_dir_selector(path_lf, "번역본 폴더:", self.ccfolia_trans_dir, 1)
        self.create_dir_selector(path_lf, "출력 폴더:", self.ccfolia_output_dir, 2)

        # 매칭 방식 선택
        match_lf = tk.LabelFrame(parent, text="매칭 방식")
        match_lf.pack(fill="x", padx=10, pady=5)

        tk.Radiobutton(
            match_lf,
            text="수동 매핑  —  번역본 이미지마다 원본 이미지를 직접 시각적으로 선택",
            variable=self.ccfolia_match_mode,
            value="manual",
            command=self._on_match_mode_change
        ).pack(anchor="w", padx=10, pady=(6, 2))

        self.ccfolia_api_match_check = tk.Checkbutton(
            match_lf,
            text="  └ API 자동 매칭 — Gemini Vision으로 번역본↔원본 이미지 자동 추천 (수동 매핑 전용)",
            variable=self.ccfolia_api_match,
            font=(self.ui_font_family, 9)
        )
        self.ccfolia_api_match_check.pack(anchor="w", padx=30, pady=(0, 2))

        model_row = tk.Frame(match_lf, bg=match_lf.cget("bg") if hasattr(match_lf, 'cget') else "SystemButtonFace")
        model_row.pack(anchor="w", padx=48, pady=(0, 6))
        tk.Label(model_row, text="모델:", font=(self.ui_font_family, 9)).pack(side="left")
        self.ccfolia_api_match_model_entry = tk.Entry(
            model_row,
            textvariable=self.ccfolia_api_match_model,
            width=32,
            font=(self.ui_font_family, 9)
        )
        self.ccfolia_api_match_model_entry.pack(side="left", padx=(4, 0))
        self._ccfolia_model_row = model_row

        tk.Radiobutton(
            match_lf,
            text="파일명 자동 매칭  —  번역본/원본 폴더에서 파일명이 동일한 것끼리 자동 연결",
            variable=self.ccfolia_match_mode,
            value="auto",
            command=self._on_match_mode_change
        ).pack(anchor="w", padx=10, pady=(2, 6))

        self._on_match_mode_change()

        # 출력 옵션
        opt_lf = tk.LabelFrame(parent, text="출력 옵션")
        opt_lf.pack(fill="x", padx=10, pady=5)

        tk.Checkbutton(
            opt_lf,
            text="ZIP으로 출력  —  출력 폴더를 .zip 파일로 압축 (코코포리아 업로드용)",
            variable=self.ccfolia_make_zip
        ).pack(anchor="w", padx=10, pady=6)

        btn_frame = tk.Frame(parent)
        btn_frame.pack(fill="x", padx=10, pady=10)

        self.ccfolia_start_btn = tk.Button(
            btn_frame,
            text="이미지 교체 시작",
            command=self.start_ccfolia_replace,
            bg="#4CAF50", fg="white",
            font=(self.ui_font_family, 12, "bold"),
            height=2
        )
        self.ccfolia_start_btn.pack(fill="x")

        hint_lf = tk.LabelFrame(parent, text="사용 방법")
        hint_lf.pack(fill="x", padx=10, pady=5)

        hint_text = (
            "1. 원본 폴더: 코코포리아 룸 ZIP 압축 해제 폴더 (__data.json + 해시명 이미지 포함)\n"
            "2. 번역본 폴더: 번역된 이미지 파일들이 있는 폴더\n"
            "3. 수동 매핑: 번역본 이미지마다 대응하는 원본 이미지를 선택\n"
            "   파일명 자동 매칭: 이미지 글자 제거 기능으로 번역 시 파일명이 동일하게 유지됨\n"
            "4. 확인 후 교체 실행 → 출력 폴더에 수정된 __data.json과 이미지 저장"
        )
        tk.Label(hint_lf, text=hint_text, justify="left", fg="#555",
                 font=(self.ui_font_family, 9)).pack(anchor="w", padx=10, pady=6)

    # ── 매칭 모드 변경 핸들러 ──────────────────────────────────────────

    def _on_match_mode_change(self):
        """수동 모드일 때만 API 자동 매칭 체크박스/모델 입력란을 활성화."""
        import tkinter as tk
        state = "normal" if self.ccfolia_match_mode.get() == "manual" else "disabled"
        self.ccfolia_api_match_check.config(state=state)
        self.ccfolia_api_match_model_entry.config(state=state)

    # ── 실행 진입점 ────────────────────────────────────────────────────

    def start_ccfolia_replace(self):
        """입력값을 검증하고 설정을 저장한 뒤, 이미지 교체 작업을 백그라운드 스레드로 시작한다."""
        from tkinter import messagebox

        src = self.ccfolia_src_dir.get().strip()
        trans = self.ccfolia_trans_dir.get().strip()
        out = self.ccfolia_output_dir.get().strip()
        mode = self.ccfolia_match_mode.get()
        make_zip = self.ccfolia_make_zip.get()

        if not src or not os.path.isdir(src):
            messagebox.showwarning("경고", "원본 폴더를 선택해주세요.")
            return
        if not trans or not os.path.isdir(trans):
            messagebox.showwarning("경고", "번역본 폴더를 선택해주세요.")
            return
        if not out:
            messagebox.showwarning("경고", "출력 폴더를 선택해주세요.")
            return
        if not os.path.exists(os.path.join(src, "__data.json")):
            messagebox.showwarning("경고", "원본 폴더에 __data.json이 없습니다.\n코코포리아 룸 압축 해제 폴더를 지정해주세요.")
            return

        api_match = self.ccfolia_api_match.get()
        api_match_model = self.ccfolia_api_match_model.get().strip() or "gemini-3.1-flash-lite-preview"

        from config import save_settings
        save_settings(
            self.settings.get("api_key", ""),
            self.settings.get("model_name", ""),
            ccfolia_src_dir=src,
            ccfolia_trans_dir=trans,
            ccfolia_output_dir=out,
            ccfolia_match_mode=mode,
            ccfolia_make_zip=make_zip,
            ccfolia_api_match=api_match,
            ccfolia_api_match_model=api_match_model
        )
        self.settings["ccfolia_src_dir"] = src
        self.settings["ccfolia_trans_dir"] = trans
        self.settings["ccfolia_output_dir"] = out
        self.settings["ccfolia_api_match"] = api_match
        self.settings["ccfolia_api_match_model"] = api_match_model

        self.ccfolia_start_btn.config(state="disabled")
        self.log("=== 코코포리아 이미지 교체 시작 ===")

        thread = threading.Thread(
            target=self._run_ccfolia_replace,
            args=(src, trans, out, make_zip, mode, api_match, api_match_model),
            daemon=True
        )
        thread.start()

    # ── 핵심 처리 로직 (백그라운드 스레드) ───────────────────────────

    def _run_ccfolia_replace(self, src_dir, trans_dir, output_dir, make_zip, match_mode, api_match=False, api_match_model="gemini-3.1-flash-lite-preview"):
        """백그라운드 스레드에서 실행: 이미지 매핑 수집 → 해시 계산 → __data.json 치환 → 파일 복사 → ZIP 생성."""
        try:
            img_exts = ('.png', '.jpg', '.jpeg')
            trans_files = [f for f in os.listdir(trans_dir) if f.lower().endswith(img_exts)]
            if not trans_files:
                self.log("오류: 번역본 폴더에 이미지 파일이 없습니다.")
                return

            src_files = [f for f in os.listdir(src_dir) if f.lower().endswith(img_exts)]
            src_files_set = set(src_files)

            # 매핑 수집: 다이얼로그는 반드시 메인(Tkinter) 스레드에서 실행해야 하므로
            # root.after()로 예약하고, threading.Event로 완료를 기다린다.
            pairs = []          # [(trans_path, orig_filename), ...]
            event = threading.Event()

            if match_mode == "auto":
                src_stem_map = {os.path.splitext(f)[0]: f for f in src_files}
                matched = {src_stem_map[os.path.splitext(f)[0]]: os.path.join(trans_dir, f)
                           for f in trans_files if os.path.splitext(f)[0] in src_stem_map}
                if not matched:
                    self.log("오류: 파일명이 일치하는 이미지가 없습니다.\n"
                             "수동 매핑 모드를 사용하거나 번역본 파일명을 원본과 동일하게 변경해주세요.")
                    return
                self.log(f"  파일명 자동 매칭: {len(matched)}쌍 발견")
                self.root.after(0, lambda: self._show_auto_confirm_dialog(
                    src_dir, matched, pairs, event))
            else:
                self.log(f"  수동 매핑 모드: 번역본 {len(trans_files)}개 이미지")
                # API 자동 매칭 사용 시 Gemini Vision으로 추천 생성
                initial_mapping = None
                if api_match:
                    self.log("  API 자동 매칭 중... (Gemini Vision)")
                    initial_mapping = self._api_prematch(trans_files, src_files, src_dir, trans_dir, api_match_model)
                    matched_count = sum(1 for v in initial_mapping.values() if v is not None)
                    self.log(f"  API 매칭 완료: {matched_count}/{len(trans_files)}개 추천")
                self.root.after(0, lambda im=initial_mapping: self._show_manual_pair_dialog(
                    src_dir, src_files, trans_dir, trans_files, pairs, event, initial_mapping=im))

            event.wait()

            if not pairs:
                self.log("취소됨.")
                return

            # ── __data.json 로드 (raw string) ─────────────────────────
            data_json_path = os.path.join(src_dir, "__data.json")
            with open(data_json_path, encoding="utf-8") as f:
                json_raw = f.read()

            # 교체 맵 생성: 원본 파일명(해시)→(새 해시, 번역본 경로, 확장자)
            # 코코포리아의 파일명은 확장자를 제외한 부분이 SHA-256 다이제스트이므로
            # 번역 이미지의 해시를 새로 계산해 __data.json 내 모든 참조를 문자열 치환한다.
            replacements = {}   # old_hash → (new_hash, trans_path, ext)
            for trans_path, orig_filename in pairs:
                old_hash = os.path.splitext(orig_filename)[0]
                ext = os.path.splitext(orig_filename)[1]
                self.log(f"  SHA-256 계산: {os.path.basename(trans_path)}")
                new_hash = _sha256_of_file(trans_path)
                replacements[old_hash] = (new_hash, trans_path, ext)
                self.log(f"    {old_hash[:12]}... → {new_hash[:12]}...{ext}")

            # ── __data.json 전체 문자열 치환 ─────────────────────────
            for old_hash, (new_hash, _, _) in replacements.items():
                json_raw = json_raw.replace(old_hash, new_hash)

            # ── 출력 폴더 복사 ────────────────────────────────────────
            os.makedirs(output_dir, exist_ok=True)
            replaced_orig = {orig_fn for _, orig_fn in pairs}

            for fn in os.listdir(src_dir):
                src_path = os.path.join(src_dir, fn)
                if fn == "__data.json":
                    continue
                if fn in replaced_orig:
                    old_hash = os.path.splitext(fn)[0]
                    new_hash, trans_path, ext = replacements[old_hash]
                    shutil.copy2(trans_path, os.path.join(output_dir, new_hash + ext))
                else:
                    shutil.copy2(src_path, os.path.join(output_dir, fn))

            with open(os.path.join(output_dir, "__data.json"), "w", encoding="utf-8") as f:
                f.write(json_raw)

            self.log(f"  출력 폴더: {output_dir}")

            # ── ZIP 생성 ──────────────────────────────────────────────
            if make_zip:
                zip_path = output_dir.rstrip("/\\") + ".zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                    for fn in os.listdir(output_dir):
                        z.write(os.path.join(output_dir, fn), fn)
                self.log(f"  ZIP 저장 완료: {zip_path}")

            self.log(f"=== 완료: {len(pairs)}개 이미지 교체됨 ===")

        except Exception as e:
            import traceback
            self.log(f"오류: {e}\n{traceback.format_exc()}")
        finally:
            self.root.after(0, lambda: self.ccfolia_start_btn.config(state="normal"))

    # ── 다이얼로그 헬퍼 (메인 스레드에서 호출) ────────────────────────

    @staticmethod
    def _visual_score(img_a, img_b):
        """
        PIL 이미지 두 장의 시각적 유사도를 0~1 사이 점수로 반환.
        API 호출 전 후보 선별용: 비율(35%) + 컬러 히스토그램(65%)
        텍스트 내용 일치도는 API 단계에서 처리.
        """
        HIST_SZ = 64

        # ① 비율 유사도
        ar_a = img_a.width / max(img_a.height, 1)
        ar_b = img_b.width / max(img_b.height, 1)
        aspect_score = 1.0 - min(abs(ar_a - ar_b) / max(ar_a, ar_b, 1e-6), 1.0)

        # ② 컬러 히스토그램 코사인 유사도
        ha = img_a.resize((HIST_SZ, HIST_SZ)).histogram()
        hb = img_b.resize((HIST_SZ, HIST_SZ)).histogram()
        dot = sum(a * b for a, b in zip(ha, hb))
        norm = (sum(a ** 2 for a in ha) * sum(b ** 2 for b in hb)) ** 0.5
        hist_score = dot / (norm + 1e-10)

        return 0.35 * aspect_score + 0.65 * hist_score

    def _api_prematch(self, trans_files, src_files, src_dir, trans_dir, model_name="gemini-3.1-flash-lite-preview"):
        """
        2단계 매칭:
          1단계: PIL 히스토그램+비율로 시각 유사도 상위 TOP_K 후보 선별 (API 없음)
          2단계: 상위 후보만 Gemini Vision에 보내 최종 확인
        반환값: {trans_filename: orig_filename or None}
        """
        import re
        import google.generativeai as genai
        from PIL import Image as PILImage
        import config

        TOP_K = 10  # 후보 수: 많을수록 정확도↑, 적을수록 500 오류 감소

        api_key = config.GEMINI_API_KEY
        if not api_key:
            self.log("    API 키가 설정되어 있지 않아 자동 매칭을 건너뜁니다.")
            return {fn: None for fn in trans_files}

        self.log(f"  사용 모델: {model_name}")
        genai.configure(api_key=api_key)
        m = genai.GenerativeModel(model_name)

        # ── 원본 이미지 전부 미리 로드 ────────────────────────────────
        self.log(f"  원본 이미지 {len(src_files)}개 로드 중...")
        src_imgs = {}
        for fn in src_files:
            try:
                src_imgs[fn] = PILImage.open(os.path.join(src_dir, fn)).convert("RGB")
            except Exception:
                src_imgs[fn] = None

        result = {}

        for idx, trans_fn in enumerate(trans_files):
            self.log(f"    [{idx + 1}/{len(trans_files)}] {trans_fn} 매칭 중...")
            trans_path = os.path.join(trans_dir, trans_fn)
            try:
                trans_img = PILImage.open(trans_path).convert("RGB")
            except Exception as e:
                self.log(f"      번역본 로드 실패: {e}")
                result[trans_fn] = None
                continue

            # ── 1단계: 시각 유사도로 상위 후보 선별 ──────────────────
            scores = []
            for fn, src_img in src_imgs.items():
                if src_img is None:
                    scores.append((fn, -1.0))
                else:
                    scores.append((fn, self._visual_score(trans_img, src_img)))
            scores.sort(key=lambda x: x[1], reverse=True)
            top_candidates = [(fn, src_imgs[fn]) for fn, _ in scores[:TOP_K] if src_imgs.get(fn)]

            if not top_candidates:
                result[trans_fn] = None
                continue

            top_names = ", ".join(fn[:12] + "..." for fn, _ in top_candidates)
            self.log(f"      시각 유사도 상위 {len(top_candidates)}개: {top_names}")

            # ── 2단계: API로 최종 확인 ────────────────────────────────
            trans_thumb = trans_img.copy()
            trans_thumb.thumbnail((512, 512))

            candidate_imgs = []
            for fn, img in top_candidates:
                thumb = img.copy()
                thumb.thumbnail((256, 256))
                candidate_imgs.append((fn, thumb))

            # 번역본은 원본에서 일본어→한국어 텍스트 교체만 된 이미지
            # → 텍스트 내용(의미) 일치도를 최우선으로 비교
            content = [
                "아래는 번역된 이미지입니다 (원본 일본어 이미지의 텍스트를 한국어로 번역한 것):",
                trans_thumb,
                f"\n다음 {len(candidate_imgs)}개는 원본 이미지 후보입니다 (일본어 텍스트 포함).\n"
                f"판단 우선순위:\n"
                f"  1순위: 번역 이미지의 한국어 텍스트와 원본의 일본어 텍스트가 같은 내용(캐릭터명·수치·설명 등)인 것\n"
                f"  2순위: 텍스트가 없거나 판별 불가 시 색상·구도가 가장 유사한 것\n"
                f"해당하는 원본의 번호(1~{len(candidate_imgs)})를 숫자 하나만 답하세요. 없으면 0.\n"
            ]
            for j, (fn, img) in enumerate(candidate_imgs):
                content += [f"{j + 1}번 원본:", img]

            try:
                resp = m.generate_content(content)
                nums = re.findall(r'\d+', resp.text.strip())
                if nums:
                    n = int(nums[0])
                    if 1 <= n <= len(candidate_imgs):
                        best = candidate_imgs[n - 1][0]
                        self.log(f"      API 선택 → {best[:16]}...")
                        result[trans_fn] = best
                        continue
            except Exception as e:
                self.log(f"      API 오류: {e} → 시각 유사도 결과로 대체")

            # API 실패 또는 0 응답 → 1단계 최상위 후보로 폴백
            fallback = scores[0][0]
            self.log(f"      시각 매칭 사용 → {fallback[:16]}...")
            result[trans_fn] = fallback

        return result

    def _show_auto_confirm_dialog(self, src_dir, matched, pairs, event):
        """모드 B: 파일명 자동 매칭 확인 다이얼로그."""
        from dialogs import CcfoliaAutoConfirmDialog
        dlg = CcfoliaAutoConfirmDialog(self.root, src_dir, matched)
        self.root.wait_window(dlg)
        if dlg.confirmed_pairs:
            pairs.extend(dlg.confirmed_pairs)
        event.set()

    def _show_manual_pair_dialog(self, src_dir, src_files, trans_dir, trans_files, pairs, event,
                                 initial_mapping=None):
        """모드 A: 수동 매핑 다이얼로그."""
        from dialogs import CcfoliaImagePairDialog
        dlg = CcfoliaImagePairDialog(self.root, src_dir, src_files, trans_dir, trans_files,
                                     initial_mapping=initial_mapping)
        self.root.wait_window(dlg)
        if dlg.result_pairs:
            pairs.extend(dlg.result_pairs)
        event.set()
