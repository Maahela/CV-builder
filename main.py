"""CV Tailor entry point.

Real implementation lives in the cv_tailor package. This module re-exports
the public surface so tests that do `import main; main.X(...)` keep working.
"""
from cv_tailor.claude_client import (_log_usage, _session_stats,
                                     claude_call, claude_call_cached,
                                     print_session_summary,
                                     reset_session_stats)
from cv_tailor.config import (load_config, load_profile, save_config,
                              save_profile)
from cv_tailor.constants import (ALWAYS_SHOW_SKILLS, APP_VERSION, BG, BORDER,
                                 BULK_DELAY_SEC, COMPANY_MAX,
                                 CONDITIONAL_SKILLS, CONFIG_FILE, DEBUG_CV,
                                 DEFAULT_OUTPUT, FG, GREEN, KEYRING_SERVICE,
                                 KEYRING_USER, MARGIN_CM, MAX_TOKENS_PROFILE,
                                 MAX_TOKENS_UNIFIED, MODEL_NAME, PAGE_H_CM,
                                 PAGE_W_CM, PANEL, PROFILE_FILE,
                                 PROFILE_SCHEMA, RATE_LIMIT_RETRY_SEC, RED,
                                 RIGHT_TAB_CM, SKILL_CATEGORIES,
                                 SKILL_LABELS, TITLE_MAX, YELLOW, ACCENT)
from cv_tailor.docx_builder import DocxBuilder
from cv_tailor.extract import extract_text_from_file
from cv_tailor.gui.main_window import MainWindow, main
from cv_tailor.gui.styles import DARK_STYLESHEET, LIGHT_STYLESHEET
from cv_tailor.gui.widgets import PlainTextEdit
from cv_tailor.profile import (ProfileManager, compress_profile,
                               safe_merge_profiles,
                               slim_profile_for_generation, trim_profile,
                               validate_cv_output)
from cv_tailor.prompts import UNIFIED_SYSTEM
from cv_tailor.utils import (build_output_path, open_file_native,
                             parse_json_response, sanitize_filename_part,
                             strip_hard_gap)
from cv_tailor.workers import (BulkRunner, ProfileBuildWorker, UnifiedWorker,
                               parse_bulk_input)

if __name__ == "__main__":
    main()
