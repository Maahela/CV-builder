"""App-wide constants: version, model, file paths, page geometry, schema."""

APP_VERSION = "1.1.0"
MODEL_NAME = "claude-sonnet-4-5"
MAX_TOKENS_UNIFIED = 3000
DEBUG_CV = True
MAX_TOKENS_PROFILE = 8000
CONFIG_FILE = "config.json"
PROFILE_FILE = "master_profile.json"
DEFAULT_OUTPUT = "output"
KEYRING_SERVICE = "cv-tailor"
KEYRING_USER = "anthropic-api-key"
COMPANY_MAX = 25
TITLE_MAX = 35
BULK_DELAY_SEC = 1.0
RATE_LIMIT_RETRY_SEC = 5

PAGE_W_CM = 21.0
PAGE_H_CM = 29.7
MARGIN_CM = 2.0
RIGHT_TAB_CM = PAGE_W_CM - 2 * MARGIN_CM  # 17cm — dynamic right-edge tab

BG = "#0d1117"
FG = "#e6edf3"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#388bfd"
GREEN = "#238636"
YELLOW = "#9e6a03"
RED = "#da3633"

PROFILE_SCHEMA = {
    "name": "", "contact": {"email": "", "phone": "", "linkedin": "",
                            "github": "", "website": ""},
    "summary": "", "experience": [], "education": [],
    "skills": {"languages": [], "frontend": [], "backend": [],
               "databases": [], "cloud": [], "ai_integrations": [],
               "third_party_apis": [], "erp": [], "other": []},
    "projects": [], "certifications": [], "volunteering": [],
    "achievements": [], "interests": []
}

ALWAYS_SHOW_SKILLS = [
    "languages", "frontend", "backend", "databases",
    "cloud", "ai_integrations", "third_party_apis",
]

CONDITIONAL_SKILLS = [
    "erp", "desktop_gui", "productivity_tools", "design_collaboration",
    "analytics_tools", "dev_tools", "creative_media",
    "soft_skills", "languages_spoken",
]

SKILL_LABELS = {
    "languages": "Languages", "frontend": "Frontend",
    "backend": "Backend", "databases": "Databases",
    "cloud": "Cloud & DevOps", "ai_integrations": "AI / Integrations",
    "third_party_apis": "Third-Party APIs", "erp": "ERP",
    "desktop_gui": "Desktop / GUI", "productivity_tools": "Productivity",
    "design_collaboration": "Design & Collab",
    "analytics_tools": "Analytics", "dev_tools": "Dev Tools",
    "creative_media": "Creative & Media",
    "soft_skills": "Soft Skills", "languages_spoken": "Languages Spoken",
}

SKILL_CATEGORIES = [(k, v) for k, v in SKILL_LABELS.items()]
