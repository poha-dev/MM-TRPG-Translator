"""
correction_mixin.py — 기존 번역 HTML 파일에 용어집 기반 단어 일괄 교체를 수행하는 Mixin 클래스.

'2차 수정' 탭의 '수정 적용' 버튼에서 사용한다.
번역 후 용어가 변경된 경우, 원본 HTML을 다시 번역하지 않고 단어만 교체할 때 사용한다.
"""
import os
import threading
import shutil

from korean_utils import apply_replacement


class CorrectionMixin:
    """HTML 번역 결과물에 용어집 기반 단어 교체를 적용하는 Mixin."""

    def apply_corrections(self):
        """입력 폴더의 HTML 파일들에 용어집을 적용하고 교체 결과를 출력 폴더에 저장한다."""
        from tkinter import messagebox
        input_dir = self.correct_input_dir.get()
        output_dir = self.correct_output_dir.get()
        glossary_file = self.correct_glossary_file.get()

        if not input_dir or not output_dir:
            messagebox.showwarning("Warning", "Please select Input HTML folder and Output folder.")
            return

        glossary = self.load_glossary_from_file(glossary_file)

        if not glossary:
            messagebox.showwarning("Warning", "Glossary file is empty or not selected. No terms will be replaced (only copying).")

        thread = threading.Thread(target=self.run_correction, args=(input_dir, output_dir, glossary))
        thread.daemon = True
        thread.start()

    def run_correction(self, input_dir, output_dir, glossary):
        """백그라운드 스레드에서 실행: HTML 파일을 하나씩 읽어 용어집의 각 항목을 apply_replacement로 교체한다."""
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Copy images folder if exists (to maintain images)
            src_img_dir = os.path.join(input_dir, "images")
            dst_img_dir = os.path.join(output_dir, "images")
            if os.path.exists(src_img_dir):
                if not os.path.exists(dst_img_dir):
                    shutil.copytree(src_img_dir, dst_img_dir)

            html_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.html')]
            total = len(html_files)

            if total == 0:
                self.msg_queue.put(("error", "No HTML files found in input directory."))
                return

            self.log(f"Starting correction for {total} files...")

            for i, filename in enumerate(html_files):
                self.update_progress(i, total, f"Correcting: {filename}...")

                src_path = os.path.join(input_dir, filename)
                dst_path = os.path.join(output_dir, filename)

                with open(src_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                for old, new in glossary.items():
                    content = apply_replacement(content, old, new)

                with open(dst_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                self.log(f"Corrected: {filename}")

            self.update_progress(total, total, "Correction Done")
            self.msg_queue.put(("done", None))

        except Exception as e:
            self.msg_queue.put(("error", f"Correction Error: {str(e)}"))
