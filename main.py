"""
main.py — CLI 진입점: 텍스트/이미지 폴더를 받아 번역 결과를 단일 텍스트 파일로 저장한다.

GUI 없이 커맨드라인에서 일괄 번역할 때 사용한다.
API 키는 settings.json 또는 .env 파일에서 로드한다.
"""
import os
import argparse
from tqdm import tqdm
from config import GEMINI_API_KEY
from file_handler import get_file_content
from translator import translate_content

def main():
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set.")
        print("Run the GUI (gui.py) and enter your API key in the Settings tab,")
        print("or copy settings.json.example to settings.json and fill in your key.")
        return

    parser = argparse.ArgumentParser(description="Japanese TRPG/Murder Mystery Translator (CLI)")
    parser.add_argument("output_file", help="Path to the output text file", default="result.txt")
    parser.add_argument("--text-dir", help="Directory containing .pdf / .txt files")
    parser.add_argument("--image-dir", help="Directory containing image files (.png / .jpg)")

    args = parser.parse_args()

    output_file = args.output_file
    text_dir = args.text_dir
    image_dir = args.image_dir

    if not text_dir and not image_dir:
        print("Error: Provide at least one of --text-dir or --image-dir.")
        return

    # Collect files from specified directories
    files_to_process = []

    if text_dir:
        if os.path.isdir(text_dir):
            files_to_process.extend(
                os.path.join(text_dir, f)
                for f in os.listdir(text_dir)
                if os.path.isfile(os.path.join(text_dir, f))
            )
        else:
            print(f"Warning: Text directory '{text_dir}' not found.")

    if image_dir:
        if os.path.isdir(image_dir):
            files_to_process.extend(
                os.path.join(image_dir, f)
                for f in os.listdir(image_dir)
                if os.path.isfile(os.path.join(image_dir, f))
            )
        else:
            print(f"Warning: Image directory '{image_dir}' not found.")

    files_to_process.sort()

    if not files_to_process:
        print("No files found to process.")
        return

    print(f"Found {len(files_to_process)} files. Starting translation...")
    print(f"Output: {output_file}")

    with open(output_file, "w", encoding="utf-8") as outfile:
        for filepath in tqdm(files_to_process, desc="Processing Files"):
            filename = os.path.basename(filepath)

            for header, content, content_type in get_file_content(filepath):
                tqdm.write(f"Translating: {filename} - {header}")

                translated_text = translate_content(content, content_type)

                outfile.write(f"{header}\n")
                outfile.write(f"{translated_text}\n\n")
                outfile.flush()   # 번역 도중 중단돼도 결과가 보존되도록 청크마다 즉시 기록

    print("\nTranslation completed!")

if __name__ == "__main__":
    main()
