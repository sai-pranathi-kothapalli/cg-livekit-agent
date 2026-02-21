"""
Prompt utilities - placeholder substitution for agent context.
"""

from typing import Optional


def substitute_context_placeholders(context: str, candidate_profile: Optional[dict]) -> str:
    """
    Replace placeholders in dashboard context with candidate profile values.
    E.g. {name} or {full_name} -> candidate name, {email} -> email, etc.
    Uses candidate_profile keys; {name} is aliased to full_name.
    Unknown placeholders are left as-is.
    """
    if not context or not context.strip():
        return context
    subs = {}
    if candidate_profile and isinstance(candidate_profile, dict):
        for k, v in candidate_profile.items():
            if k and isinstance(k, str) and k != "_id":
                val = str(v).strip() if v is not None else ""
                # Skip substituting internal "id" (MongoDB doc id) so we don't leak it into speech
                if k == "id" and len(val) == 24 and val.isalnum():
                    continue
                subs[k] = val
        # Alias: {name} -> full_name
        if "full_name" in subs:
            subs["name"] = subs["full_name"]
        elif "full_name" in candidate_profile:
            subs["name"] = str(candidate_profile["full_name"]).strip() if candidate_profile["full_name"] else ""

        # Format list-based fields for better prompt injection
        if isinstance(candidate_profile.get("skills"), list):
            subs["skills"] = ", ".join(candidate_profile["skills"])
        if isinstance(candidate_profile.get("projects"), list):
            subs["projects"] = "\n- ".join([""] + candidate_profile["projects"])

    # Replace {key} with value for each key in subs
    for key, value in subs.items():
        if key:
            context = context.replace("{" + key + "}", value)

    # Replace common placeholders that might be missing from candidate_profile with empty string
    # This prevents the LLM from seeing literal {full_name} etc. and echoing it
    common_placeholders = ["full_name", "email", "graduation_degree", "skills", "name"]
    for placeholder in common_placeholders:
        if "{" + placeholder + "}" in context:
            # Only replace if not already substituted (not in subs)
            if placeholder not in subs:
                context = context.replace("{" + placeholder + "}", "")

    return context
