"""
image_mixin.py — PDF 이미지 추출(배치) 및 Gemini 기반 이미지 글자 제거 기능을 담은 Mixin 클래스.

TRPGTranslatorApp이 이 Mixin을 상속해 '1차 번역' 탭의 PDF 이미지 추출 버튼과
'이미지 글자 제거' 탭의 기능을 모두 사용한다.
"""
import os
import threading
import webbrowser

from file_handler import extract_pdf_images_raw


class ImageMixin:
    """PDF 이미지 일괄 추출 및 이미지 글자 제거 기능을 제공하는 Mixin."""

    # ── PDF 이미지 추출 ────────────────────────────────────────────────

    def start_extract_pdf_images(self):
        """선택된 PDF 폴더에서 모든 이미지를 추출하고 HTML 갤러리를 생성한다."""
        from tkinter import messagebox
        text_dir = self.text_dir.get()
        output_dir = self.output_dir.get()

        if not text_dir or not os.path.isdir(text_dir):
            messagebox.showwarning("Warning", "텍스트/PDF 폴더를 먼저 선택해주세요.")
            return
        if not output_dir:
            messagebox.showwarning("Warning", "결과물 저장 폴더를 먼저 선택해주세요.")
            return

        pdf_files = []
        for root, _, files in os.walk(text_dir):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, f))

        if not pdf_files:
            messagebox.showwarning("Warning", "선택한 폴더에 PDF 파일이 없습니다.")
            return

        self.extract_images_btn.config(state='disabled')
        self.start_btn.config(state='disabled')
        self.glossary_btn.config(state='disabled')

        thread = threading.Thread(target=self.run_extract_pdf_images, args=(pdf_files, output_dir))
        thread.daemon = True
        thread.start()

    def run_extract_pdf_images(self, pdf_files, output_dir):
        """백그라운드 스레드에서 실행: PDF별로 이미지를 추출하고 완료 후 HTML 갤러리를 브라우저로 연다."""
        try:
            all_saved = []
            for filepath in pdf_files:
                base_name = os.path.splitext(os.path.basename(filepath))[0]
                img_dir = os.path.join(output_dir, f"{base_name}_images")
                self.log(f"이미지 추출 중: {os.path.basename(filepath)}")
                saved = extract_pdf_images_raw(filepath, img_dir)
                all_saved.extend(saved)
                self.log(f"  → {len(saved)}개 이미지 저장됨: {img_dir}")

            if not all_saved:
                self.log("추출된 이미지가 없습니다.")
            else:
                gallery_path = os.path.join(output_dir, "extracted_images_gallery.html")
                self._build_image_gallery_html(all_saved, gallery_path, output_dir)
                self.log(f"HTML 갤러리 생성 완료: {gallery_path}")
                webbrowser.open(f"file:///{gallery_path.replace(os.sep, '/')}")

        except Exception as e:
            self.log(f"이미지 추출 오류: {e}")
        finally:
            def re_enable():
                self.extract_images_btn.config(state='normal')
                self.start_btn.config(state='normal')
                self.glossary_btn.config(state='normal')
            self.root.after(0, re_enable)

    def _build_image_gallery_html(self, saved_list, gallery_path, base_dir):
        """추출된 이미지 목록을 받아 브라우저에서 볼 수 있는 HTML 갤러리 파일을 생성한다."""
        rows = []
        for item in saved_list:
            rel = os.path.relpath(item["path"], os.path.dirname(gallery_path)).replace(os.sep, '/')
            rows.append(
                f'<div class="card">'
                f'<img src="{rel}" loading="lazy" />'
                f'<p>페이지 {item["page"]} &nbsp;|&nbsp; {item["width"]}×{item["height"]} &nbsp;|&nbsp; {item["filename"]}</p>'
                f'</div>'
            )
        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>PDF 이미지 갤러리</title>
<style>
  body {{ font-family: sans-serif; background: #1e1e1e; color: #ddd; margin: 0; padding: 16px; }}
  h1 {{ font-size: 1.2em; margin-bottom: 12px; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .card {{ background: #2d2d2d; border-radius: 6px; padding: 8px; max-width: 320px; }}
  .card img {{ max-width: 100%; height: auto; display: block; border-radius: 4px; }}
  .card p {{ margin: 6px 0 0; font-size: 0.75em; color: #aaa; word-break: break-all; }}
</style>
</head>
<body>
<h1>추출된 이미지 — {len(saved_list)}개</h1>
<div class="grid">
{"".join(rows)}
</div>
</body>
</html>"""
        with open(gallery_path, "w", encoding="utf-8") as f:
            f.write(html)

    # ── 이미지 글자 제거 (Image Cleaner) ─────────────────────────────

    def preview_image_clean(self):
        """입력 폴더의 첫 번째 이미지를 Gemini로 처리해 원본과 결과를 나란히 보여주는 미리보기 창을 연다."""
        from tkinter import messagebox
        from dialogs import ImagePreviewDialog
        input_dir = self.ic_input_dir.get()
        if not input_dir or not os.path.exists(input_dir):
            messagebox.showwarning("Warning", "입력 폴더를 확인해주세요.")
            return

        image_file = None
        for root, _, files in os.walk(input_dir):
            for f in files:
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_file = os.path.join(root, f)
                    break
            if image_file:
                break

        if not image_file:
            messagebox.showwarning("Warning", "이미지 파일을 찾을 수 없습니다.")
            return

        self.ic_status_label.config(text="미리보기 생성 중...")
        self.ic_start_btn.config(state="disabled")

        def run():
            from PIL import Image
            import translator
            try:
                orig = Image.open(image_file)
                cleaned = translator.clean_image(
                    orig,
                    self.ic_prompt.get(),
                    self.ic_alpha_enabled.get(),
                    self.ic_api_key.get().strip(),
                    self.ic_model_name.get().strip()
                )

                if cleaned:
                    def show():
                        ImagePreviewDialog(self.root, orig, cleaned, os.path.basename(image_file))
                        self.ic_status_label.config(text="미리보기 완료")
                        self.ic_start_btn.config(state="normal")
                    self.root.after(0, show)
                else:
                    self.msg_queue.put(("error", "이미지 처리에 실패했습니다. API 설정을 확인해주세요."))
            except Exception as e:
                self.msg_queue.put(("error", str(e)))
            finally:
                self.root.after(0, lambda: self.ic_start_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def start_batch_clean(self):
        """입력 폴더의 모든 이미지를 재귀적으로 수집해 Gemini 이미지 클리너로 일괄 처리한다. 하위 폴더 구조를 그대로 유지한다."""
        import tkinter as tk
        from tkinter import messagebox
        input_dir = self.ic_input_dir.get()
        output_dir = self.ic_output_dir.get()

        if not input_dir or not output_dir:
            messagebox.showwarning("Warning", "입력 및 결과 저장 폴더를 지정해주세요.")
            return

        image_files = []
        for root, _, files in os.walk(input_dir):
            for f in files:
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    rel_path = os.path.relpath(root, input_dir)
                    if rel_path == '.':
                        rel_path = ''
                    image_files.append((os.path.join(root, f), rel_path))

        if not image_files:
            messagebox.showwarning("Warning", "처리할 이미지가 없습니다.")
            return

        self.ic_start_btn.config(state="disabled")
        self.log_area.config(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state="disabled")

        def run_batch():
            import translator
            from PIL import Image
            total = len(image_files)
            for i, (path, rel_dir) in enumerate(image_files):
                filename = os.path.basename(path)
                self.update_progress(i, total, f"Cleaning: {filename}")
                self.log(f"Processing ({i+1}/{total}): {filename}")

                try:
                    orig = Image.open(path)
                    cleaned = translator.clean_image(
                        orig,
                        self.ic_prompt.get(),
                        self.ic_alpha_enabled.get(),
                        self.ic_api_key.get().strip(),
                        self.ic_model_name.get().strip()
                    )

                    if cleaned:
                        target_dir = os.path.join(output_dir, rel_dir)
                        if not os.path.exists(target_dir):
                            os.makedirs(target_dir)
                        cleaned.save(os.path.join(target_dir, filename))
                        self.log(f"Saved to: {os.path.join(rel_dir, filename)}")
                    else:
                        self.log(f"Failed to clean: {filename}")
                except Exception as e:
                    self.log(f"Error processing {filename}: {e}")

            self.msg_queue.put(("done", "Batch processing complete!"))
            self.msg_queue.put(("ic_done", None))

        threading.Thread(target=run_batch, daemon=True).start()
