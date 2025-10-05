# agent_ai.py - Lightweight AI-assisted agent using sentence-transformers embeddings + rule-based fallbacks.
# Note: This will download a small embedding model (paraphrase-MiniLM-L6-v2) on first run.
from sentence_transformers import SentenceTransformer, util
import re
import platform
import os
from pathlib import Path

MODEL_NAME = os.environ.get("VC_EMBED_MODEL", "paraphrase-MiniLM-L6-v2")
_model = None

# safe patterns - will require confirmation
FORBIDDEN_PATTERNS = [
    r"rm\s+-rf", r":\s*>", r"dd\s+", r"mkfs", r"shutdown\s+-h", r"reboot", r"passwd", r"chmod\s+777",
    r"chown\s+", r"apt-get\s+remove", r"apt\s+remove", r"pip\s+uninstall", r"npm\s+uninstall", r"sudo\s+-?i?"
]

def load_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def is_forbidden(cmd):
    for p in FORBIDDEN_PATTERNS:
        if re.search(p, cmd, flags=re.IGNORECASE):
            return True
    return False

def detect_language(text):
    if re.search(r'[\u0600-\u06FF]', text):
        return 'fa'
    return 'en'

def choose_installer(system):
    if system == "Windows":
        return "choco"
    elif system == "Darwin":
        return "brew"
    else:
        return "apt"

def parse_install_intent(text):
    t = text.lower()
    m = re.search(r"(?:install|نصب|pip install|apt install|apt-get install|brew install|npm install|choco install)\s+([a-zA-Z0-9_\-\.]+)", t)
    if m:
        pkg = m.group(1)
        if 'pip' in t or pkg.endswith('.py') or pkg.islower():
            installer = 'pip'
        elif 'npm' in t or 'node' in t:
            installer = 'npm'
        elif 'brew' in t:
            installer = 'brew'
        elif 'choco' in t:
            installer = 'choco'
        else:
            installer = choose_installer(platform.system())
        return pkg, installer
    m2 = re.search(r"نصب\s+([^\s،]+)", text)
    if m2:
        return m2.group(1), choose_installer(platform.system())
    return None, None

# Intent templates (human readable) -> macro generator function
_INTENT_TEMPLATES = [
    {"name":"install_package", "template":"install PACKAGE", "score_weight":1.0},
    {"name":"open_terminal", "template":"open terminal", "score_weight":1.0},
    {"name":"open_google", "template":"open google", "score_weight":1.0},
    {"name":"search_web", "template":"search for QUERY", "score_weight":1.0},
    {"name":"scan_book", "template":"scan book", "score_weight":1.0},
    {"name":"open_app", "template":"open app NAME", "score_weight":1.0}
]

def _build_embeddings():
    model = load_model()
    texts = [t["template"] for t in _INTENT_TEMPLATES]
    emb = model.encode(texts, convert_to_tensor=True)
    return emb

# generate macro from intent name + original text
def _generate_macro_from_intent(intent_name, text):
    # try rule-based parsing for parameters where possible
    if intent_name == "install_package":
        pkg, installer = parse_install_intent(text)
        if not pkg:
            return None
        steps = []
        if installer == 'pip':
            steps.append({'action':'shell','cmd':f'pip install {pkg}'})
        elif installer == 'npm':
            steps.append({'action':'shell','cmd':f'npm install -g {pkg}'})
        elif installer == 'brew':
            steps.append({'action':'shell','cmd':f'brew install {pkg}'})
        elif installer == 'choco':
            steps.append({'action':'shell','cmd':f'choco install {pkg} -y'})
        else:
            steps.append({'action':'shell','cmd':f'sudo apt-get update && sudo apt-get install -y {pkg}'})
        steps.append({'action':'speak','text':f'Installed {pkg} (attempted with {installer})'})
        return {'type':'macro','steps':steps, 'requires_confirmation': any(is_forbidden(s.get('cmd','')) for s in steps)}
    if intent_name == "open_terminal":
        return {'type':'macro','steps':[{'action':'terminal'}], 'requires_confirmation': False}
    if intent_name == "open_google":
        return {'type':'macro','steps':[{'action':'open','target':'https://www.google.com'}], 'requires_confirmation': False}
    if intent_name == "search_web":
        # extract query
        m = re.search(r"(?:search for|search|جستجو کن برای|جستجو برای|جستجو)\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            return {'type':'macro','steps':[{'action':'search','q':q}], 'requires_confirmation': False}
        # fallback: ask user later
        return None
    if intent_name == "scan_book":
        steps = [
            {'action':'terminal'},
            {'action':'wait','seconds':1},
            {'action':'speak','text':'Please place the book on the scanner and press Enter.'},
            {'action':'wait','seconds':1},
            {'action':'shell','cmd':"echo Scanning book > scan_result.txt"},
            {'action':'open','target':'scan_result.txt'}
        ]
        return {'type':'macro','steps':steps, 'requires_confirmation': False}
    if intent_name == "open_app":
        # try to extract app name
        m = re.search(r"(?:open|باز کن|launch)\s+(.+)", text, flags=re.IGNORECASE)
        if m:
            app = m.group(1).strip()
            # naive mapping
            if 'chrome' in app or 'کروم' in app or 'google' in app:
                cmd = 'start chrome' if platform.system()=='Windows' else 'google-chrome || chromium || open -a \"Google Chrome\"'
                return {'type':'macro','steps':[{'action':'shell','cmd':cmd}], 'requires_confirmation': False}
            if 'vscode' in app or 'code'==app.lower():
                return {'type':'macro','steps':[{'action':'shell','cmd':'code'}], 'requires_confirmation': False}
            # fallback: try open as URL or shell
            return {'type':'macro','steps':[{'action':'shell','cmd':f'{app}'}], 'requires_confirmation': is_forbidden(app)}
        return None
    return None

# main function: text -> macro using embeddings + fallback rules
def text_to_macro_ai(text, threshold=0.6):
    model = load_model()
    emb_text = model.encode(text, convert_to_tensor=True)
    emb_templates = _build_embeddings()
    scores = util.cos_sim(emb_text, emb_templates)[0].tolist()
    # find best
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_score = scores[best_idx]
    intent = _INTENT_TEMPLATES[best_idx]['name']
    # convert cosine to 0..1 scale (since cosine can be between -1..1)
    sim = (best_score + 1)/2
    # threshold check
    if sim >= threshold:
        macro = _generate_macro_from_intent(intent, text)
        if macro:
            macro['__intent'] = intent
            macro['__score'] = float(sim)
            return macro
    # fallback to None
    return None

# fallback: use simple rule-based parser if AI mapping fails
def text_to_macro_rule(text):
    # simple reuse of earlier patterns
    # install intent
    pkg, installer = parse_install_intent(text)
    if pkg:
        steps = [{'action':'shell','cmd':f'pip install {pkg}'}]
        return {'type':'macro','steps':steps, 'requires_confirmation': any(is_forbidden(s.get('cmd','')) for s in steps)}
    # open intent
    if 'google' in text.lower() or 'گوگل' in text:
        return {'type':'macro','steps':[{'action':'open','target':'https://www.google.com'}], 'requires_confirmation': False}
    if 'scan' in text.lower() or 'اسکن' in text:
        return {'type':'macro','steps':[{'action':'terminal'},{'action':'wait','seconds':1},{'action':'shell','cmd':\"echo Scanning book > scan_result.txt\"},{'action':'open','target':'scan_result.txt'}], 'requires_confirmation': False}
    return None

def text_to_macro(text, ai_threshold=0.6):
    # try AI mapping first
    try:
        macro = text_to_macro_ai(text, threshold=ai_threshold)
        if macro:
            return macro
    except Exception as e:
        print('AI mapping failed, falling back to rules:', e)
    # fallback rules
    return text_to_macro_rule(text)
