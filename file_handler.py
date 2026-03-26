"""
file_handler.py — PDF, TXT, 이미지 파일에서 번역 가능한 콘텐츠 청크를 추출하는 함수 모음.

get_file_content()가 핵심 함수로, 파일 형식에 따라 텍스트·표·이미지를
(header, content, content_type) 튜플로 yield한다.
PDF 처리 시 색상/하이라이트 정보를 내부 태그(<c=>, <b>, <hl=>)로 인코딩한다.
"""
import fitz  # PyMuPDF
from PIL import Image
import os
import io
import re

# Pre-compiled patterns
_COLOR_TAG_PATTERN = re.compile(r'<c=#[0-9a-fA-F]{6}>|</c>|<b>|</b>')

def scan_pdf_images(filepath):
    """
    Scans a PDF and returns a list of dictionaries with image metadata/content.
    Used for the pre-selection GUI.
    """
    images_found = []
    # Let exceptions propagate to GUI for handling
    doc = fitz.open(filepath)
    for i, page in enumerate(doc):
        image_list = page.get_images(full=True)
        if image_list:
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                try:
                    image_data = Image.open(io.BytesIO(image_bytes))
                    width, height = image_data.size

                    # Downsample to thumbnail for the selection dialog to save memory.
                    # Original dimensions are preserved in width/height metadata.
                    thumb = image_data.copy()
                    thumb.thumbnail((500, 500), Image.Resampling.LANCZOS)

                    images_found.append({
                        "id": f"[{i+1}페이지 - 이미지_{img_index+1}]", # Matches logic in get_file_content
                        "page": i + 1,
                        "image": thumb,  # Thumbnail PIL Image (memory-efficient)
                        "size": f"{width}x{height}",
                        "width": width,
                        "height": height
                    })
                except Exception as img_err:
                    print(f"Skipping PDF image on page {i+1}: {img_err}")
    
    return images_found

def extract_pdf_images_raw(filepath, output_dir):
    """
    Extracts all images from a PDF and saves them WITHOUT re-encoding (lossless).
    Uses raw bytes directly from PyMuPDF to preserve original quality.
    Returns a list of dicts: {page, filename, path, width, height, ext}
    """
    os.makedirs(output_dir, exist_ok=True)
    saved = []
    try:
        doc = fitz.open(filepath)
        seen_xrefs = set()
        for i, page in enumerate(doc):
            image_list = page.get_images(full=True)
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    base_image = doc.extract_image(xref)
                    ext = base_image.get("ext", "png")
                    raw_bytes = base_image["image"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    filename = f"p{i+1:03d}_{img_index+1:02d}.{ext}"
                    out_path = os.path.join(output_dir, filename)
                    with open(out_path, "wb") as f:
                        f.write(raw_bytes)

                    saved.append({
                        "page": i + 1,
                        "filename": filename,
                        "path": out_path,
                        "width": width,
                        "height": height,
                        "ext": ext
                    })
                except Exception as img_err:
                    print(f"Skipping image xref={xref} on page {i+1}: {img_err}")
    except Exception as e:
        print(f"Error extracting images from {filepath}: {e}")

    return saved


def get_file_content(filepath, allowed_image_ids=None, extract_color=False, embed_all_images=False):
    """파일에서 번역 단위(청크)를 순차적으로 yield한다.

    반환 형식: (header_str, content, content_type)
      - header_str: 청크 식별자 (예: "[3페이지]", "[2~4페이지]", "[파일명]")
      - content:    str(텍스트), PIL.Image(이미지), list[list[str]](테이블)
      - content_type: 'text' | 'image' | 'pdf_image' | 'pdf_image_embed' | 'pdf_table'

    allowed_image_ids: 이 set에 포함된 ID의 이미지만 'pdf_image'로 yield. None이면 전부 허용.
    extract_color:     True이면 PDF 텍스트 스팬의 색상/볼드 정보를 내부 태그로 인코딩.
    embed_all_images:  True이면 allowed_image_ids 밖의 이미지도 'pdf_image_embed'로 yield (번역 제외, 삽입용).
    """
    ext = os.path.splitext(filepath)[1].lower()
    filename = os.path.basename(filepath)

    if ext == '.pdf':
        try:
            doc = fitz.open(filepath)
            text_buffer = ""
            buffer_start_page = 0
            
            for i, page in enumerate(doc):
                # 1. Text Content
                if extract_color:
                    text = ""
                    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
                    for block in blocks:
                        if "lines" not in block:
                            continue
                        for line in block["lines"]:
                            for span in line["spans"]:
                                span_text = span["text"]
                                if not span_text.strip():
                                    text += span_text
                                    continue

                                color_int = span["color"]
                                hex_color = f"#{color_int:06x}" if isinstance(color_int, int) else "#000000"
                                is_bold = bool(span.get("flags", 0) & 16)

                                tagged = f'<c={hex_color}>{span_text}</c>' if hex_color != "#000000" else span_text
                                if is_bold:
                                    tagged = f'<b>{tagged}</b>'
                                text += tagged
                            text += "\n"
                else:
                    text = page.get_text()
                
                # 문장 이어붙이기: 페이지가 문장 중간에서 끊기는 경우를 처리한다.
                # 종결 부호로 끝나지 않으면 다음 페이지와 합산해 하나의 청크로 yield한다.
                if text.strip():
                    # 태그를 제거한 순수 텍스트로 종결 여부를 판단 (태그 자체가 종결 부호를 포함하지 않도록)
                    stripped_raw = _COLOR_TAG_PATTERN.sub('', text).strip()

                    terminators = ['.', '!', '?', '。', '」', '』', '！', '？']
                    is_complete = any(stripped_raw.endswith(t) for t in terminators)

                    if not is_complete:
                        if not text_buffer:
                            buffer_start_page = i + 1
                        text_buffer += text

                        # 버퍼가 너무 커지면 강제 yield — 무한 버퍼링 방지
                        if len(text_buffer) > 4000:
                            yield f"[{buffer_start_page}~{i+1}페이지]", text_buffer, 'text'
                            text_buffer = ""
                    else:
                        # Complete sentence(s) found.
                        if text_buffer:
                            # Flush buffer + current text
                            combined_text = text_buffer + text
                            yield f"[{buffer_start_page}~{i+1}페이지]", combined_text, 'text'
                            text_buffer = ""
                        else:
                            # Just current page
                            yield f"[{i+1}페이지]", text, 'text'

                # Note: If we have a lingering buffer at the very last page, flushing it is needed.

                # 2. Image Content (Yield immediately to keep images somewhat close to their page)
                # Issue: If we buffer text, images might appear "before" the text chunk they belong to ends.
                # However, usually images are illustrative. We yield them with their specific page number.
                image_list = page.get_images(full=True)
                if image_list:
                    for img_index, img_info in enumerate(image_list):
                        # Calculate ID first
                        img_id = f"[{i+1}페이지 - 이미지_{img_index+1}]"

                        # FILTER CHECK
                        is_allowed = allowed_image_ids is None or img_id in allowed_image_ids
                        if not is_allowed and not embed_all_images:
                            continue  # Skip entirely

                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]

                        try:
                            image_data = Image.open(io.BytesIO(image_bytes))
                            ctype = 'pdf_image' if is_allowed else 'pdf_image_embed'
                            yield img_id, image_data, ctype
                        except Exception as img_err:
                            print(f"Skipping PDF image on page {i+1}: {img_err}")

            # Flush remaining buffer if any
            if text_buffer:
                 yield f"[{buffer_start_page}~{len(doc)}페이지]", text_buffer, 'text'

        except Exception as e:
            print(f"Error reading PDF {filename}: {e}")

    elif ext == '.txt':
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
            yield "[1페이지]", text, 'text'
        except UnicodeDecodeError:
            # Fallback for other encodings if needed, but utf-8 is standard
            try:
                with open(filepath, 'r', encoding='cp949') as f:
                    text = f.read()
                yield "[1페이지]", text, 'text'
            except Exception as e:
                print(f"Error reading TXT {filename}: {e}")

    elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
        try:
            img = Image.open(filepath)
            yield f"[{filename}]", img, 'image'
        except Exception as e:
            print(f"Error opening image {filename}: {e}")
    
    else:
        print(f"Unsupported file format: {filename}")


def detect_scanned_pdf(filepath: str) -> list:
    """
    텍스트 레이어 없이 이미지만 있는 페이지 번호 목록을 반환한다 (1-based).
    빈 리스트 반환 시 정상 PDF (텍스트 추출 가능).
    """
    try:
        doc = fitz.open(filepath)
        scanned_pages = [
            i + 1
            for i, page in enumerate(doc)
            if not page.get_text().strip() and page.get_images()
        ]
        doc.close()
        return scanned_pages
    except Exception:
        return []
