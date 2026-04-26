"""Profile cleaning, compression, validation, merge, and ProfileManager."""
import json

from .constants import MAX_TOKENS_PROFILE, PROFILE_SCHEMA
from .utils import parse_json_response

_FIELD_SHORTS = {
    "achievements": "ach", "responsibilities": "resp",
    "organization": "org", "description": "desc",
    "technologies": "tech", "highlights": "pts",
}
_DROP_TOP_KEYS = {"interests", "certifications"}
_DROP_EXP_KEYS = {"location"}


def trim_profile(profile):
    """Drop empty values so we don't pay tokens for blank keys."""
    if not profile:
        return {}
    out = {}
    for k, v in profile.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, dict):
            sub = {sk: sv for sk, sv in v.items() if sv not in (None, "", [])}
            if sub:
                out[k] = sub
        elif isinstance(v, list):
            cleaned = [x for x in v if x not in (None, "", [], {})]
            if cleaned:
                out[k] = cleaned
        else:
            out[k] = v
    return out


def slim_profile_for_generation(profile):
    """Drop noise fields Claude doesn't need. Keeps the cached payload small."""
    if not profile:
        return {}
    out = {}
    for k, v in profile.items():
        if k in _DROP_TOP_KEYS or v in (None, "", [], {}):
            continue
        if k == "experience" and isinstance(v, list):
            out[k] = [
                {ek: ev for ek, ev in exp.items()
                 if ek not in _DROP_EXP_KEYS and ev not in (None, "", [], {})}
                for exp in v if isinstance(exp, dict)
            ]
        elif isinstance(v, dict):
            sub = {sk: sv for sk, sv in v.items()
                   if sv not in (None, "", [], {})}
            if sub:
                out[k] = sub
        elif isinstance(v, list):
            cleaned = []
            for item in v:
                if isinstance(item, dict):
                    ci = {ik: iv for ik, iv in item.items()
                          if iv not in (None, "", [], {})}
                    if ci:
                        cleaned.append(ci)
                elif item not in (None, "", [], {}):
                    cleaned.append(item)
            if cleaned:
                out[k] = cleaned
        else:
            out[k] = v
    return out


def compress_profile(profile):
    """Slim, serialize tight, and shorten common keys to save input tokens."""
    slim = slim_profile_for_generation(profile)
    text = json.dumps(slim, separators=(",", ":"))
    for long, short in _FIELD_SHORTS.items():
        text = text.replace(f'"{long}":', f'"{short}":')
    return text


def validate_cv_output(cv_data, master_profile):
    """Strip any skill or achievement not present in the master profile."""
    real_skills = set()
    for cat_skills in master_profile.get("skills", {}).values():
        if isinstance(cat_skills, list):
            for s in cat_skills:
                real_skills.add(s.lower().strip())
    for cat, skills in cv_data.get("skills", {}).items():
        if isinstance(skills, list):
            cv_data["skills"][cat] = [
                s for s in skills if s.lower().strip() in real_skills
            ]
    real_ach = {a.lower().strip()
                for a in master_profile.get("achievements", [])}
    if real_ach:
        cv_data["achievements"] = [
            a for a in cv_data.get("achievements", [])
            if a.lower().strip() in real_ach
        ]
    return cv_data


def safe_merge_profiles(old, new):
    """Guard against Claude dropping data: keep any old list items missing
    from new (by name/title key)."""
    if not old:
        return new
    if not new:
        return old
    out = dict(new)
    for list_key, id_key in (("experience", "title"), ("projects", "name"),
                             ("education", "degree"),
                             ("certifications", "name"),
                             ("volunteering", "role")):
        old_list = old.get(list_key) or []
        new_list = out.get(list_key) or []
        seen = {(it.get(id_key) or "").strip().lower() for it in new_list}
        for it in old_list:
            key = (it.get(id_key) or "").strip().lower()
            if key and key not in seen:
                new_list.append(it)
                seen.add(key)
        out[list_key] = new_list
    old_sk = old.get("skills") or {}
    new_sk = out.get("skills") or {}
    merged_sk = {}
    for k in set(list(old_sk.keys()) + list(new_sk.keys())):
        merged = list(new_sk.get(k) or [])
        lower = {s.lower() for s in merged}
        for s in old_sk.get(k) or []:
            if s.lower() not in lower:
                merged.append(s)
                lower.add(s.lower())
        merged_sk[k] = merged
    if merged_sk:
        out["skills"] = merged_sk
    old_c = old.get("contact") or {}
    new_c = out.get("contact") or {}
    for k, v in old_c.items():
        if v and not new_c.get(k):
            new_c[k] = v
    if new_c:
        out["contact"] = new_c
    if old.get("name") and not out.get("name"):
        out["name"] = old["name"]
    return out


class ProfileManager:
    """Build and merge the master profile via Claude."""

    def __init__(self, client):
        """Hold Anthropic client."""
        self.client = client

    def build_new(self, texts):
        """Create a fresh profile from extracted document texts."""
        from .claude_client import claude_call
        combined = "\n\n---\n\n".join(texts)
        schema_str = json.dumps(PROFILE_SCHEMA, separators=(",", ":"))
        system = (
            "Extract ONLY the information explicitly present in the CV "
            "document(s) into this exact JSON schema. Return ONLY valid "
            "JSON, no fences, no commentary.\n\n"
            "STRICT EXTRACTION RULES:\n"
            "- Copy text verbatim where possible; minor rewording only.\n"
            "- NEVER invent metrics, numbers, percentages, dates, awards, "
            "projects, skills, languages, or achievements not stated in "
            "the source documents.\n"
            "- If a field is not in the source, leave it empty.\n"
            "- Experience entries use keys: title, company, location, "
            "start_date, end_date, responsibilities (list of bullets).\n"
            "- Project entries use keys: name, description, technologies "
            "(list), link, highlights (list of bullets).\n"
            "- Volunteering entries use keys: role, organization, "
            "start_date, end_date, description.\n"
            "- Education entries use keys: degree, institution, location, "
            "start_date, end_date, details.\n"
            "- Skills must use the category keys in the schema exactly.\n\n"
            "SCHEMA: " + schema_str
        )
        text = claude_call(self.client, system, combined, MAX_TOKENS_PROFILE,
                           call_name="profile_build")
        return parse_json_response(text)

    def merge(self, existing, texts):
        """Merge new document texts into existing profile."""
        from .claude_client import claude_call
        combined = "\n\n---\n\n".join(texts)
        compact = json.dumps(existing, separators=(",", ":"))
        system = (
            "Merge new CV information into the existing profile. Add new "
            "roles, projects, skills found in the source documents. "
            "Deduplicate. NEVER remove existing data. NEVER invent "
            "content not present in either the existing profile or the "
            "new documents (no fabricated metrics, awards, projects, "
            "skills, or achievements). Use the same schema keys as the "
            "existing profile. Return the complete updated profile as "
            "JSON only, no fences."
        )
        user = f"EXISTING:{compact}\n\nNEW:\n{combined}"
        text = claude_call(self.client, system, user, MAX_TOKENS_PROFILE,
                           call_name="profile_merge")
        merged = parse_json_response(text)
        return safe_merge_profiles(existing, merged)
