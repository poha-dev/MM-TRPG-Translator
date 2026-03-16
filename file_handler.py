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
_COLOR_TAG_PATTERN = re.compile(r'<c=#[0-9a-fA-F]{6}>|</c>|<b>|</b>|<hl=#[0-9a-fA-F]{6}>|</hl>')

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
    extract_color:     True이면 PDF 텍스트 스팬의 색상/볼드/하이라이트를 내부 태그로 인코딩.
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
                    # 단계 1: 드로잉 기반 색상 사각형 수집
                    # find_tables() 이전에 먼저 실행해야 "하이라이트 박스를 표로 잘못 인식"하는 것을 방지할 수 있다.
                    drawing_hl_rects = []  # [(fitz.Rect, "#rrggbb")] — colored fills
                    try:
                        for d in page.get_drawings():
                            fill = d.get("fill")
                            if not fill or len(fill) < 3:
                                continue
                            r_c, g_c, b_c = int(fill[0]*255), int(fill[1]*255), int(fill[2]*255)
                            if (r_c, g_c, b_c) in ((255, 255, 255), (0, 0, 0)):
                                continue
                            # Filter 1: size — highlights must cover at least one text line (30pt × 8pt)
                            rect = fitz.Rect(d["rect"])
                            if rect.width < 30 or rect.height < 8:
                                continue
                            # Filter 2: brightness — highlights are bright colors (avg RGB ≥ 80)
                            if (r_c + g_c + b_c) / 3 < 80:
                                continue
                            drawing_hl_rects.append((rect, f"#{r_c:02x}{g_c:02x}{b_c:02x}"))
                        # Filter 3: count cap — >30 rects means decorative background, discard all
                        if len(drawing_hl_rects) > 30:
                            drawing_hl_rects = []
                    except Exception:
                        pass

                    # 단계 2: 표 탐지 — 색상 드로잉 rect와 겹치는 "표"는 하이라이트 박스이므로 제외
                    tables_on_page = []
                    table_rects = []
                    try:
                        tab_finder = page.find_tables()
                        for t in tab_finder.tables:
                            t_rect = fitz.Rect(t.bbox)
                            if any(t_rect.intersects(dr) for dr, _ in drawing_hl_rects):
                                # This "table" is actually a highlight background — skip it
                                continue
                            tables_on_page.append(t)
                            table_rects.append(t_rect)
                    except Exception:
                        pass

                    # 단계 3: 하이라이트 rect 전체 수집 (드로잉 기반 + 어노테이션 기반)
                    hl_rects = list(drawing_hl_rects)  # 드로잉 기반으로 시작
                    try:
                        for annot in page.annots():
                            if annot.type[1] == 'Highlight':
                                col = annot.colors.get("stroke") or annot.colors.get("fill") or (1, 1, 0)
                                r_c, g_c, b_c = int(col[0]*255), int(col[1]*255), int(col[2]*255)
                                hl_rects.append((annot.rect, f"#{r_c:02x}{g_c:02x}{b_c:02x}"))
                    except Exception:
                        pass

                    text = ""
                    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
                    for block in blocks:
                        if "lines" not in block:
                            continue
                        # Skip blocks that overlap with a table area
                        block_rect = fitz.Rect(block["bbox"])
                        if any(block_rect.intersects(tr) for tr in table_rects):
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
                                # Highlight: outermost wrapper
                                if hl_rects:
                                    span_rect = fitz.Rect(span["bbox"])
                                    hl_color = next(
                                        (hc for hr, hc in hl_rects if span_rect.intersects(hr)),
                                        None
                                    )
                                    if hl_color:
                                        tagged = f'<hl={hl_color}>{tagged}</hl>'
                                text += tagged
                            text += "\n"
                else:
                    text = page.get_text()
                    tables_on_page = []
                
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

                # 2. Table Content (yield before images, flush text buffer first)
                for t_idx, table in enumerate(tables_on_page):
                    try:
                        table_data = table.extract()  # 2D list of strings (None for merged cells)
                        if not table_data:
                            continue

                        rows = len(table_data)
                        cols = max((len(r) for r in table_data), default=0)

                        # 장식용 테두리나 오탐 표 제거:
                        # - 1열짜리는 테두리 선일 가능성이 높음
                        # - 200셀 초과는 페이지 전체를 덮는 오탐일 가능성이 높음
                        total_cells = rows * cols
                        if cols < 2 or total_cells > 200:
                            print(f"Skipping likely false-positive table on page {i+1}: {rows}r x {cols}c ({total_cells} cells)")
                            continue

                        # Flush text buffer before table
                        if text_buffer:
                            yield f"[{buffer_start_page}~{i+1}페이지]", text_buffer, 'text'
                            text_buffer = ""
                        yield f"[{i+1}페이지 - 테이블_{t_idx+1}]", table_data, 'pdf_table'
                    except Exception as te:
                        print(f"Skipping table on page {i+1}: {te}")

                # 3. Image Content (Yield immediately to keep images somewhat close to their page)
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
