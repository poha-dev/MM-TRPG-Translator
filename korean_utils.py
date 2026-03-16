import re

# Pre-compiled pattern: 조사 앞에 오는 선택적 공백/구두점 + 조사 (다음 글자가 한글이 아닌 경우)
_JOSA_PATTERN = re.compile(r'^([\s\'"\]\)]*)(은|는|이|가|을|를|과|와)(?![가-힣])')

def has_batchim(char):
    """
    Checks if the last Korean character has a batchim (final consonant).
    """
    if '가' <= char <= '힣':
        return (ord(char) - ord('가')) % 28 > 0
    return False

def get_josa(word, josa_type):
    """
    Returns the correct Josa for the given word based on josa_type.
    josa_type examples: '은/는', '이/가', '을/를', '과/와'
    """
    if not word:
        return josa_type.split('/')[0] # Default

    # Find the last Korean character to accurately determine batchim
    last_char = word[-1]
    for char in reversed(word):
        if '가' <= char <= '힣' or char.isdigit() or char.isalpha():
            last_char = char
            break
    
    has_final = False
    if '가' <= last_char <= '힣':
        has_final = (ord(last_char) - ord('가')) % 28 > 0
    elif last_char.isdigit():
        # Heuristic for numbers: 1, 3, 6, 7, 8, 0 often sound like consonants
        has_final = last_char in ['1', '3', '6', '7', '8', '0']
    elif last_char.isalpha():
        # Rough heuristic for English consonants: L, M, N, R, etc.
        has_final = last_char.lower() in ['l', 'm', 'n', 'r', 'b', 'c', 'd', 'g', 'k', 'p', 't']
    
    # Select Josa
    parts = josa_type.split('/')
    if len(parts) != 2:
        return josa_type
    
    if has_final:
        return parts[0] # 은, 이, 을, 과
    else:
        return parts[1] # 는, 가, 를, 와

def correct_josa_in_text(text):
    """
    Scans text for patterns like [Noun](은/는) and fixes them.
    However, our strategy is replacing "A" with "B".
    So we look for "B[Josa]" in the *replaced* text.
    
    Regex approach:
    Find the replaced word, check the next character.
    If next char is a Josa (은,는,이,가,을,를,과,와), swap it if incorrect.
    """
    josa_pairs = {
        '은': '은/는', '는': '은/는',
        '이': '이/가', '가': '이/가',
        '을': '을/를', '를': '을/를',
        '과': '과/와', '와': '과/와'
    }
    
    # We will need a way to perform this correction specifically around the replaced term.
    # Global correction might adhere to wrong targets.
    # But for now, let's provide a utility that checks a specific word + josa combination.
    pass

def apply_replacement(text, old_word, new_word):
    """
    Replaces old_word with new_word in text, ONLY if it appears to be a distinct word 
    (or at least not a suffix of another Korean noun).
    Also adjusts the immediately following Josa.
    """
    if old_word not in text:
        return text

    # We iterate to find all occurrences and fix Josa
    current_text = text
    offset = 0
    
    # Known Josa list
    josas = ['은', '는', '이', '가', '을', '를', '과', '와']
    
    while True:
        try:
            idx = current_text.find(old_word, offset)
            if idx == -1:
                break
            
            # 1. Check Preceding Character (Left Boundary)
            # If the character BEFORE the match is a Korean syllable, we assume it's part of a compound word (e.g. 갑자기).
            # In that case, we SKIP this replacement.
            is_valid_start = True
            if idx > 0:
                prev_char = current_text[idx-1]
                if '가' <= prev_char <= '힣':
                    # It is part of a previous Korean word -> Skip
                    is_valid_start = False
            
            if not is_valid_start:
                offset = idx + 1
                continue

            # Perform Replacement
            prefix = current_text[:idx]
            suffix = current_text[idx+len(old_word):]
            
            # Find Josa in suffix, allowing spaces and punctuation before it
            new_suffix = suffix

            # Match optional spaces/punctuation followed by a Josa
            josa_match = _JOSA_PATTERN.match(suffix)
            
            if josa_match:
                 sp_punct = josa_match.group(1)
                 original_josa = josa_match.group(2)
                 josa_group = None
                 
                 # Identify group
                 if original_josa in ['은', '는']: josa_group = '은/는'
                 elif original_josa in ['이', '가']: josa_group = '이/가'
                 elif original_josa in ['을', '를']: josa_group = '을/를'
                 elif original_josa in ['과', '와']: josa_group = '과/와'
                 
                 if josa_group:
                     correct = get_josa(new_word, josa_group)
                     if correct != original_josa:
                         # Replace the Josa char at the matching position
                         new_suffix = sp_punct + correct + suffix[len(sp_punct)+1:]
            
            current_text = prefix + new_word + new_suffix
            offset = len(prefix) + len(new_word) # Move past this replacement
            
        except Exception as e:
            print(f"Error in replacement: {e}")
            break
            
    return current_text

