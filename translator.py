"""
translator.py — Gemini API 클라이언트 설정, 번역/교열/용어집 추출/이미지 클리닝 함수 모음.

모든 API 호출 함수는 429(Rate Limit), 500/504(서버 오류)에 대해 지수 백오프 재시도를 수행한다.
"""
import google.generativeai as genai
import config  # 전역 프롬프트/설정 접근을 위해 모듈 자체를 임포트
import time
import json
import io
from PIL import Image

# 전역 모델 인스턴스 — configure_genai() 호출 시 초기화된다.
model = None
refine_model = None
image_cleaner_model = None

def configure_genai(api_key, model_name, glossary=None, cleaner_api_key=None, cleaner_model_name=None):
    """Gemini 클라이언트를 초기화한다.

    glossary가 제공되면 config.update_system_prompt()로 시스템 프롬프트에 용어집을 주입한다.
    cleaner_api_key/cleaner_model_name이 제공되면 이미지 클리너 전용 모델도 초기화한다.
    모든 안전 필터는 TRPG 시나리오 번역 특성상 BLOCK_NONE으로 설정한다.
    반환값: (success: bool, message: str)
    """
    global model, refine_model, image_cleaner_model
    
    if not api_key:
        return False, "API Key is missing."

    try:
        genai.configure(api_key=api_key)
        
        # Update prompts dynamically with glossary if provided
        prompts = config.update_system_prompt(config.TRANSLATION_RULES, glossary)
        
        # Initialize Translation Model
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=prompts["system_prompt"],
            generation_config=genai.types.GenerationConfig(temperature=0.0),
            safety_settings={
                'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
            }
        )

        # Initialize Refine Model
        refine_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=prompts["refine_system_prompt"],
            generation_config=genai.types.GenerationConfig(temperature=0.0),
            safety_settings={
                'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
            }
        )

        # Initialize Image Cleaner Model if provided
        if cleaner_api_key and cleaner_model_name:
            # We assume current configuration handles the primary API key.
            # If they are different, we might need a separate configuration call if the SDK allows.
            # However, usually users use the same or we re-configure for that call.
            # For now, let's keep it simple.
            image_cleaner_model = genai.GenerativeModel(
                model_name=cleaner_model_name,
                generation_config=genai.types.GenerationConfig(temperature=0.0),
                safety_settings={
                    'HARM_CATEGORY_HARASSMENT': 'OFF',
                    'HARM_CATEGORY_HATE_SPEECH': 'OFF',
                    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'OFF',
                    'HARM_CATEGORY_DANGEROUS_CONTENT': 'OFF'
                }
            )

        return True, "Configured successfully."
    except Exception as e:
        return False, str(e)

def validate_api_connection(api_key, model_name):
    """API 키와 모델명을 검증한다. count_tokens()를 사용해 생성 토큰을 소비하지 않는다.

    반환값: (True, "연결 성공") 또는 (False, 오류 메시지)
    """
    if not api_key:
        return False, "API Key가 입력되지 않았습니다."

    try:
        genai.configure(api_key=api_key)
        m = genai.GenerativeModel(model_name)
        # count_tokens validates both API key and model name without generating content
        m.count_tokens("test")
        return True, "연결 성공"
    except Exception as e:
        error_msg = str(e)
        if "400" in error_msg or "API key not valid" in error_msg:
             return False, "유효하지 않은 API Key입니다.\n키 값을 다시 확인해주세요."
        elif "404" in error_msg or "models/" in error_msg:
             return False, f"모델명 '{model_name}'을(를) 찾을 수 없습니다.\n모델 이름을 확인해주세요 (예: gemini-1.5-flash)."
        elif "429" in error_msg:
             return False, "API 사용량 한도(Quota)를 초과했습니다.\n잠시 후 다시 시도하거나 요금제를 확인해주세요."
        else:
             return False, f"API 연결 오류:\n{error_msg}"

def optimize_prompts(user_rules, api_key, model_name):
    """
    Uses Gemini to generated optimized system prompts based on user provided rules.
    Returns (success, new_system_prompt, new_refine_prompt)
    """
    if not api_key:
        return False, "API Key is missing.", "API Key is missing."
        
    try:
        # Use a temporary config just for this call if needed, 
        # or just assume genai is configured. Better to explicit configure.
        genai.configure(api_key=api_key)
        temp_model = genai.GenerativeModel(model_name)
        
        # Meta-Prompt
        meta_prompt = f"""
You are an expert prompt engineer. The user will provide a set of "Translation Rules" for a Translator tool (Source Language -> Target Language) tailored for TRPG/Murder Mystery scenarios.

Your goal is to REWRITE the internal "System Prompt" and "Refine Prompt" to perfectly reflect these new rules and the desired tone/atmosphere.

[Current System Prompt Template]
{config.DEFAULT_SYSTEM_PROMPT}

[Current Refine Prompt Template]
{config.DEFAULT_REFINE_SYSTEM_PROMPT}

[User's New Rules]
{user_rules}

[Task]
1. Analyze the user's new rules.
2. Rewrite the [Current System Prompt Template] to incorporate these new rules strictly. 
   - IF the user's rules specify a different source language (e.g., English), CHANGE the "Japanese" references in the template to that language.
   - Key the output as "system_prompt".
3. Rewrite the [Current Refine Prompt Template] to incorporate these new rules strictly. Key it as "refine_system_prompt".

[Output Format]
Return JSON format ONLY:
{{
  "system_prompt": "...",
  "refine_system_prompt": "..."
}}
"""
        response = temp_model.generate_content(meta_prompt)
        text = response.text.strip()
        
        # Basic markdown cleanup
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return True, data.get("system_prompt", ""), data.get("refine_system_prompt", "")
        
    except Exception as e:
        error_msg = str(e)
        friendly_msg = f"오류 발생: {error_msg}"
        
        if "400" in error_msg or "API key not valid" in error_msg:
             friendly_msg = "유효하지 않은 API Key입니다."
        elif "404" in error_msg:
             friendly_msg = f"모델명 '{model_name}'을(를) 찾을 수 없습니다."
        elif "429" in error_msg:
             friendly_msg = "API 사용량 한도(Quota)를 초과했습니다."
             
        return False, friendly_msg, friendly_msg

# Translation table for full-width -> half-width conversion (built once at module load)
_FULLWIDTH_TABLE = str.maketrans(
    {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
    | {0x3000: ' '}  # Ideographic Space -> regular space
)

def normalize_fullwidth_to_halfwidth(text):
    """
    Converts full-width ASCII characters (e.g., １, Ａ, （, ）, ：) to their half-width equivalents.
    Uses str.translate() with a pre-built table for C-level performance.
    """
    if not isinstance(text, str):
        return text
    return text.translate(_FULLWIDTH_TABLE)

def _table_to_tsv(table_data):
    """Converts a 2D list (from PyMuPDF table.extract()) to a TSV string for AI input."""
    rows = []
    for row in table_data:
        cells = [str(cell).strip() if cell is not None else "" for cell in row]
        rows.append("\t".join(cells))
    return "\n".join(rows)

def _tsv_to_table(tsv_text, original_rows, original_cols):
    """Parses TSV text back to a 2D list. Pads/trims to match original dimensions."""
    result = []
    for line in tsv_text.strip().split("\n"):
        cells = line.split("\t")
        # Ensure correct column count
        while len(cells) < original_cols:
            cells.append("")
        result.append(cells[:original_cols])
    # Ensure correct row count
    while len(result) < original_rows:
        result.append([""] * original_cols)
    return result[:original_rows]

def translate_content(content, content_type):
    """
    Sends content to Gemini for translation.
    content: str (text), PIL.Image (image), or list[list[str]] (pdf_table)
    content_type: 'text', 'image', 'pdf_image', or 'pdf_table'
    """
    global model

    if content_type == 'text':
        # Apply full-width to half-width character normalization before translation
        content = normalize_fullwidth_to_halfwidth(content)
    
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            if content_type == 'text':
                if isinstance(content, str) and not content.strip():
                    return "(내용 주석: 공백 페이지 또는 텍스트 없음)"
                
                response = model.generate_content(content)
                return response.text.strip()
            
            elif content_type == 'image' or content_type == 'pdf_image':
                # Apply the same logic for PDF images.
                # If needed, we can prepend "(이미지)" programmatically here or in the prompts,
                # but the user asked for "(이미지) Result" format.
                try:
                    response = model.generate_content(content)
                    result = response.text.strip()
                except ValueError:
                    # Occurs when "The `response.text` quick accessor requires the response to contain a valid `Part`"
                    # This often happens if the model sees no text or refuses to translate (safety/finish_reason 1).
                    # Since we set safety to BLOCK_NONE, it's likely just empty or "stop".
                    return "(번역 내용 없음)"

                # Special formatting for PDF images as requested: "(이미지) ..."
                if content_type == 'pdf_image':
                     return f"(이미지) {result}"
                return result
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str: # Quota exceeded or rate limit
                wait = retry_delay * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                print(f"Rate limit hit. Retrying in {wait}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            elif "500" in error_str or "Internal error" in error_str or "504" in error_str or "Deadline Exceeded" in error_str: # Server error / Timeout
                print(f"Server error or Timeout (50x). Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                return f"번역 중 오류 발생: {str(e)}"

    return "번역 실패: 재시도 횟수 초과"

# refine_model is initialized in configure_genai

def refine_content(text):
    """
    Sends translated text to Gemini for polishing.
    """
    # If text indicates error or empty, skip
    if "번역 내용 없음" in text or "번역 실패" in text or not text.strip():
        return text

    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            response = refine_model.generate_content(text)
            return response.text.strip()
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                wait = retry_delay * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                print(f"Refine Rate limit hit. Retrying in {wait}s...")
                time.sleep(wait)
            elif "500" in error_str or "Internal error" in error_str or "504" in error_str or "Deadline Exceeded" in error_str:
                print(f"Refine Server error or Timeout. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                return f"교열 중 오류: {text} ({e})"

    return text # Return original if refine fails

def extract_glossary(text_content):
    """
    Scans the provided text content using Gemini to extract proper nouns
    and key scenario terms, outputting them in 'Original text:Korean' format.
    """
    global model
    
    prompt = f"""
다음은 TRPG/머더미스터리 시나리오의 전체 또는 일부 텍스트입니다.
이 문서 전체를 살펴보고 자주 등장하거나 일관된 번역이 필수적인 '고유명사(인명, 지명 등)' 및 '핵심 시나리오 용어(트릭, 특수 키워드)'를 강제로 추출해 주세요.

출력 규칙:
1. 반드시 '원문:한국어번역문' 형태로 한 줄에 하나씩 별도의 텍스트 없이 출력할 것. 
    (예: ララ:라라, Smith:스미스, 東京:도쿄)
    *주의*: 콜론(:) 왼쪽에는 반드시 문서에 사용된 "원래 언어 텍스트 그대로"를 유지해야 합니다. 
    왼쪽 항목을 한국어 발음으로 적지 마세요. (잘못된 예: 라라:라라, 스미스:스미스)
2. 부가적인 설명이나 인사말, 마크다운 코드블록(```)은 절대 포함하지 말 것.
3. 중복되는 단어는 제외할 것.
4. 추출된 단어가 없으면 아무것도 출력하지 말 것.

[텍스트 시작]
{text_content}
[텍스트 끝]
"""

    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            # We don't want Temperature=0.0 to prevent it from finding words, but model already has it. 
            # We can override config if needed, but 0.0 is fine for extraction tasks.
            response = model.generate_content(prompt, stream=True)
            result = ""
            for chunk in response:
                if chunk.text:
                    result += chunk.text
                    yield chunk.text
            
            # Clean up potential codeblock from markdown response (done after streaming finishes if needed by caller, or here but we yield parts)
            # Since we yield, the caller will get the markdown tags too and will need to clean it up or ignore it.
            # However, for real-time progress, we just yield the text string chunks.
            
            return
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                print(f"Glossary Extraction Rate limit hit. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            elif "500" in error_str or "Internal error" in error_str or "504" in error_str or "Deadline Exceeded" in error_str:
                print(f"Glossary Extraction Server error or Timeout. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                 print(f"Glossary Extraction Error: {str(e)}")
                 yield f"Error: {str(e)}"
                 return
                 
def clean_image(pil_image, prompt, alpha_enabled, api_key, model_name):
    """
    Cleans text from image using Gemini Pro Image.
    Returns cleaned PIL.Image.
    """
    try:
        # Re-configure if needed (if cleaner uses different key)
        genai.configure(api_key=api_key)
        m = genai.GenerativeModel(model_name)
        
        # Prepare content
        # If alpha is enabled and image has alpha, we might need to handle it.
        # Most LLMs expect RGB. We can send RGB and re-apply alpha later if needed,
        # or just send the image as is if the SDK Handles it.
        
        original_mode = pil_image.mode
        alpha = None
        if original_mode == 'RGBA':
            alpha = pil_image.getchannel('A')
            input_image = pil_image.convert('RGB')
        else:
            input_image = pil_image

        # Nanobanana API style prompt often requires specific instructions.
        # The user provided "캐릭터나 그림은 유지하고 글자만 자연스럽게 지워줘"
        
        response = m.generate_content([prompt, input_image])
        
        # Assuming the model returns an image part in the response.
        # Note: Standard Gemini returns text. If 'nanobanana' implies a specific multi-modal output,
        # we need to check how to extract the image. 
        # For gemini-pro-vision / gemini-1.5, usually it's text.
        # HOWEVER, the user mentioned "nanobanana api" which often refers to a specific tuning or a wrapper
        # that returns an image. If it's a standard Gemini call, it won't "return" a cleaned image directly 
        # unless it's a specific "image-to-image" model.
        # Assuming 'gemini-3-pro-image-preview' supports image generation/editing output bits.
        
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                cleaned_img = Image.open(io.BytesIO(part.inline_data.data))
                
                # Ensure the output image matches the input image size
                if cleaned_img.size != pil_image.size:
                    cleaned_img = cleaned_img.resize(pil_image.size, Image.Resampling.LANCZOS)
                
                if alpha_enabled and alpha:
                    if cleaned_img.mode != 'RGBA':
                        cleaned_img = cleaned_img.convert('RGBA')
                    cleaned_img.putalpha(alpha)
                
                return cleaned_img
        
        return None # No image returned
        
    except Exception as e:
        print(f"Error in clean_image: {e}")
        return None

def validate_image_cleaner_api(api_key, model_name):
    """Validates connection for Image Cleaner."""
    if not api_key: return False, "API Key가 없습니다."
    try:
        genai.configure(api_key=api_key)
        m = genai.GenerativeModel(model_name)
        # Minimal test - might not be possible without an image for some models, 
        # but we try a text prompt.
        m.generate_content("Hello")
        return True, "연결 성공"
    except Exception as e:
        return False, str(e)
