"""
config.py — 전역 설정, 기본 프롬프트, 그리고 settings.json / prompts.json 입출력을 관리한다.

모듈 로드 시 load_settings()와 load_prompts()가 자동으로 호출되어
전역 변수(GEMINI_API_KEY, MODEL_NAME, SYSTEM_PROMPT 등)를 초기화한다.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

SETTINGS_FILE = "settings.json"
PROMPTS_FILE = "prompts.json"
RULES_FILE = "prompt.txt"

DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_IMAGE_CLEANER_MODEL = "gemini-3-pro-image-preview"
DEFAULT_IMAGE_CLEANER_PROMPT = "캐릭터나 그림은 유지하고 글자만 자연스럽게 지워줘"

# --- Default Prompts (Fallbacks) ---
DEFAULT_TRANSLATION_RULES = """1. 직독직해 하지 말고 한국인이 봤을 때 어색하지 않도록 자연스럽게 번역해줘.
2. 그렇다고 해서 내용을 요약하지는 마. 내용 전문을 번역해줘야되.
3. 원문에 적혀있는 글자 기호는 그대로 써줘. 특히 「 」 ※ · 이런것들. 없으면 넣지마
4. 원문에 글머리 없으면 넣지 말고, ** 같은 마크다운 볼드 처리도 하지마
5. 문장 기호는 사용하되, 한자 병기와 강조 기호(**)는 절대 사용하지 않는다.
6. 원본(텍스트의 <c> 태그나 이미지의 실제 글씨)에 검정색이 아닌 특정 색상의 글씨가 있다면, 번역 시 해당 부분을 반드시 <c=#HEX코드>번역된 텍스트</c> 형태로 감싸서 출력해. (예: 붉은색 글씨는 <c=#ff0000>위험</c>)
7. 입력 텍스트에 <b>...</b> 태그가 있으면 번역 후에도 반드시 해당 태그를 그대로 유지해. (예: <b>굵은 글씨</b>)
"""

DEFAULT_SYSTEM_PROMPT = f"""
당신은 일본어 머더미스터리 및 TRPG 시나리오 번역 전문가입니다.
아래의 규칙을 엄격히 준수하여 입력된 내용을 한국어로 번역하세요.

[번역 규칙]
{DEFAULT_TRANSLATION_RULES}

입력된 형식(텍스트, HTML 포함)을 파괴하지 마세요. 특히 HTML <span> 태그나 <br> 태그 구조는 반드시 원본 그대로 출력 결과에 포함해야 합니다.
위 규칙에 따라 번역 결과만 출력하세요. 부가적인 설명(예: "네, 알겠습니다", "번역 결과입니다")은 생략하세요.
"""

DEFAULT_REFINE_SYSTEM_PROMPT = """
당신은 TRPG 및 소설 전문 교열자입니다. 
입력된 한국어 텍스트를 읽고, 한국인이 읽기에 더 자연스럽고 매끄러운 "한국어다운 문장"으로 다듬어주세요.

[교열 규칙]
1. 원문의 의미를 절대 훼손하지 마세요. (내용 추가/삭제 금지)
2. 번역투(수동태 남발, 일본어식 조사 등)를 자연스러운 한국어 문장으로 수정하세요.
3. 문맥에 맞게 어휘와 어미를 다듬어 몰입감을 높이세요.
4. 기호(「 」 등)는 원본 그대로 유지하세요.
5. 오로지 수정된 텍스트만 출력하세요. 부가적인 설명은 생략하세요.
"""

# --- Global State (Managed by load_settings/load_prompts) ---
GEMINI_API_KEY = ""
MODEL_NAME = DEFAULT_MODEL
TRANSLATION_RULES = DEFAULT_TRANSLATION_RULES
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT
REFINE_SYSTEM_PROMPT = DEFAULT_REFINE_SYSTEM_PROMPT

# Image Cleaner Settings
IMAGE_CLEANER_API_KEY = ""
IMAGE_CLEANER_MODEL_NAME = DEFAULT_IMAGE_CLEANER_MODEL
IMAGE_CLEANER_PROMPT = DEFAULT_IMAGE_CLEANER_PROMPT
IMAGE_CLEANER_ALPHA_ENABLED = True

def load_settings():
    """settings.json에서 API 키, 모델명, 이미지 클리너 설정을 불러와 전역 변수에 반영한다."""
    global GEMINI_API_KEY, MODEL_NAME
    global IMAGE_CLEANER_API_KEY, IMAGE_CLEANER_MODEL_NAME, IMAGE_CLEANER_PROMPT, IMAGE_CLEANER_ALPHA_ENABLED
    
    settings = {
        "api_key": GEMINI_API_KEY,
        "model_name": MODEL_NAME,
        "image_cleaner_api_key": IMAGE_CLEANER_API_KEY,
        "image_cleaner_model_name": IMAGE_CLEANER_MODEL_NAME,
        "image_cleaner_prompt": IMAGE_CLEANER_PROMPT,
        "image_cleaner_alpha_enabled": IMAGE_CLEANER_ALPHA_ENABLED
    }
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings.update(saved)
                GEMINI_API_KEY = settings.get("api_key", GEMINI_API_KEY)
                MODEL_NAME = settings.get("model_name", MODEL_NAME)
                IMAGE_CLEANER_API_KEY = settings.get("image_cleaner_api_key", IMAGE_CLEANER_API_KEY)
                IMAGE_CLEANER_MODEL_NAME = settings.get("image_cleaner_model_name", IMAGE_CLEANER_MODEL_NAME)
                IMAGE_CLEANER_PROMPT = settings.get("image_cleaner_prompt", IMAGE_CLEANER_PROMPT)
                IMAGE_CLEANER_ALPHA_ENABLED = settings.get("image_cleaner_alpha_enabled", IMAGE_CLEANER_ALPHA_ENABLED)
        except Exception as e:
            print(f"Error loading settings: {e}")
            
    return settings

def save_settings(api_key, model_name, **kwargs):
    """API 키와 모델명, 그리고 추가 키워드 인자를 settings.json에 저장한다."""
    global GEMINI_API_KEY, MODEL_NAME
    GEMINI_API_KEY = api_key
    MODEL_NAME = model_name
    
    settings = {"api_key": api_key, "model_name": model_name}
    settings.update(kwargs)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def load_prompts():
    """prompt.txt(번역 규칙)와 prompts.json(시스템 프롬프트)을 읽어 전역 변수를 갱신한다. 파일이 없으면 기본값을 사용한다."""
    global TRANSLATION_RULES, SYSTEM_PROMPT, REFINE_SYSTEM_PROMPT
    
    # 1. Load translation rules from prompt.txt (user-editable plain text).
    #    If present and non-empty, overrides the built-in DEFAULT_TRANSLATION_RULES.
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    TRANSLATION_RULES = content
        except Exception as e:
            print(f"Error loading rules: {e}")

    # 2. Load full system prompts from prompts.json, overriding in-memory defaults.
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                SYSTEM_PROMPT = data.get("system_prompt", SYSTEM_PROMPT)
                REFINE_SYSTEM_PROMPT = data.get("refine_system_prompt", REFINE_SYSTEM_PROMPT)
        except Exception as e:
            print(f"Error loading prompts: {e}")
            
    return {
        "rules": TRANSLATION_RULES,
        "system_prompt": SYSTEM_PROMPT,
        "refine_system_prompt": REFINE_SYSTEM_PROMPT
    }

def update_system_prompt(base_rules, glossary=None):
    """
    번역 규칙과 용어집을 조합해 시스템 프롬프트를 동적으로 생성한다.

    base_rules에 색상 태그 규칙(<c=>) 또는 일관성 규칙이 없으면 자동으로 추가한다.
    glossary가 전달되면 '[우선순위 1위: 고유명사 사전]' 섹션을 규칙 끝에 삽입한다.
    생성된 system_prompt와 refine_system_prompt를 dict로 반환한다.
    """
    global SYSTEM_PROMPT, REFINE_SYSTEM_PROMPT

    rules = base_rules

    # 색상 태그 규칙이 없으면 추가 — 이미지 번역 시 색상 복원에 필요
    if "<c=" not in rules:
        # 현재 마지막 규칙 번호 파악 후 다음 번호로 추가
        import re as _re
        nums = [int(m) for m in _re.findall(r'^\d+', rules, flags=_re.MULTILINE)]
        next_num = (max(nums) + 1) if nums else 6
        rules += f"\n{next_num}. 원본(텍스트의 <c> 태그나 이미지의 실제 글씨)에 검정색이 아닌 특정 색상의 글씨가 있다면, 번역 시 해당 부분을 반드시 <c=#HEX코드>번역된 텍스트</c> 형태로 감싸서 출력해. (예: 붉은색 글씨는 <c=#ff0000>위험</c>)\n"

    # 동일 표현 일관성 규칙이 없으면 추가 — 번역 결과의 용어 통일을 강제
    if "문맥" not in rules and "일관성" not in rules:
        import re as _re
        nums = [int(m) for m in _re.findall(r'^\d+', rules, flags=_re.MULTILINE)]
        next_num = (max(nums) + 1) if nums else 8
        rules += f"{next_num}. 문장 구조 일관성 강화: 동일하거나 유사한 형태의 문장 구조, 혹은 특정 속성 명칭(비닉, 은닉, 비밀 등)이 문서 내 반복되어 등장할 경우, 절대로 상황에 따라 다르게 의역하거나 유의어로 대체하지 말고 이전 번역과 토씨 하나 틀리지 않고 100% 똑같은 단어와 구조로 번역해.\n"

    # Inject Glossary Terms
    if glossary and len(glossary) > 0:
        glossary_lines = [
            "\n[우선순위 1위: 고유명사 및 용어 사전 (반드시 준수할 것)]",
            "문장 내에 아래의 일본어 단어가 포함되어 있다면, 제시된 한국어 단어로 100% 동일하게 치환하여 번역하세요. (어떤 의역이나 변형도 허용되지 않음)",
        ]
        glossary_lines.extend(f"- '{jp}' -> '{kr}'" for jp, kr in glossary.items())
        glossary_lines.append("")
        rules += "\n".join(glossary_lines) + "\n"

    # Rebuild system prompt
    current_system_prompt = f"""
당신은 일본어 머더미스터리 및 TRPG 시나리오 번역 전문가입니다.
아래의 규칙을 엄격히 준수하여 입력된 내용을 한국어로 번역하세요.

[번역 규칙]
{rules}

입력된 형식(텍스트, HTML 포함)을 파괴하지 마세요. 특히 HTML <span> 태그나 <br> 태그 구조는 반드시 원본 그대로 출력 결과에 포함해야 합니다.
"""

    return {
        "system_prompt": current_system_prompt,
        "refine_system_prompt": REFINE_SYSTEM_PROMPT
    }

def save_prompts(rules, system_prompt, refine_system_prompt):
    """번역 규칙을 prompt.txt에, 시스템 프롬프트를 prompts.json에 저장하고 전역 변수를 갱신한다."""
    global TRANSLATION_RULES, SYSTEM_PROMPT, REFINE_SYSTEM_PROMPT
    
    TRANSLATION_RULES = rules
    SYSTEM_PROMPT = system_prompt
    REFINE_SYSTEM_PROMPT = refine_system_prompt
    
    success = True
    
    try:
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            f.write(rules)
    except Exception as e:
        print(f"Error saving rules: {e}")
        success = False

    try:
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
             json.dump({
                 "system_prompt": system_prompt,
                 "refine_system_prompt": refine_system_prompt
             }, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving prompts: {e}")
        success = False
        
    return success

# ── 프리셋 관련 함수 ─────────────────────────────────────────────────────

def load_presets() -> list:
    """settings.json 에서 presets 목록을 반환한다."""
    if not os.path.exists(SETTINGS_FILE):
        return []
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("presets", [])
    except Exception:
        return []


def _read_settings_raw() -> dict:
    """settings.json 전체 dict를 반환 (없으면 빈 dict)."""
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_settings_raw(data: dict) -> bool:
    """settings.json 전체를 dict로 덮어쓴다."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing settings: {e}")
        return False


def save_preset(preset: dict) -> bool:
    """이름이 같은 프리셋은 덮어쓰고, 없으면 추가한다."""
    data = _read_settings_raw()
    presets = data.get("presets", [])
    name = preset.get("name", "")
    idx = next((i for i, p in enumerate(presets) if p.get("name") == name), None)
    if idx is not None:
        presets[idx] = preset
    else:
        presets.append(preset)
    data["presets"] = presets
    return _write_settings_raw(data)


def delete_preset(name: str) -> bool:
    """이름으로 프리셋을 삭제한다."""
    data = _read_settings_raw()
    presets = [p for p in data.get("presets", []) if p.get("name") != name]
    data["presets"] = presets
    return _write_settings_raw(data)


load_settings()
load_prompts()
