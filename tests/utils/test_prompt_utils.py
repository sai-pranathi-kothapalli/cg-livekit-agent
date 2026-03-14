import pytest
from utils.prompt_utils import substitute_context_placeholders

def test_substitute_context_placeholders_basic():
    """Test basic substitution of name and email."""
    context = "Hello {name}, your email is {email}."
    profile = {"full_name": "John Doe", "email": "john@example.com"}
    result = substitute_context_placeholders(context, profile)
    assert result == "Hello John Doe, your email is john@example.com."

def test_substitute_context_placeholders_skills_list():
    """Test skill list formatting."""
    context = "Skills: {skills}"
    profile = {"skills": ["Python", "Docker", "Pytest"]}
    result = substitute_context_placeholders(context, profile)
    assert result == "Skills: Python, Docker, Pytest"

def test_substitute_context_placeholders_projects_list():
    """Test project list formatting."""
    context = "Projects: {projects}"
    profile = {"projects": ["Alpha", "Beta"]}
    result = substitute_context_placeholders(context, profile)
    assert "Projects:" in result
    assert "- Alpha" in result
    assert "- Beta" in result

def test_substitute_context_placeholders_fallbacks():
    """Test fallback values when profile data is missing."""
    context = "Hello {name}, we see you have {skills}."
    profile = {}
    result = substitute_context_placeholders(context, profile)
    assert result == "Hello Candidate, we see you have your technical background."

def test_substitute_context_placeholders_empty_context():
    """Test behavior with empty context."""
    assert substitute_context_placeholders("", {}) == ""
    assert substitute_context_placeholders(None, {}) is None

def test_substitute_context_placeholders_id_protection():
    """Verify MongoDB-style IDs are not substituted if key is 'id'."""
    context = "ID: {id}"
    profile = {"id": "60cdd0b4188710dab0db4104"} # 24 chars alnum
    result = substitute_context_placeholders(context, profile)
    # Since it matched the skip condition, it won't be in subs, so it hits fallback or stays {id}
    # {id} is not in fallbacks, so stays literal {id}
    assert result == "ID: {id}"
