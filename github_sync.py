import os
import streamlit as st

def get_github_config():
    """Возвращает конфигурацию GitHub для синхронизации, если она настроена в secrets или env."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    branch = os.getenv("GITHUB_BRANCH", "main")
    try:
        if hasattr(st, "secrets"):
            gh_secrets = st.secrets.get("github", {})
            token = token or gh_secrets.get("token")
            repo = repo or gh_secrets.get("repo")
            branch = gh_secrets.get("branch", branch)
    except Exception:
        # Если secrets.toml не создан или пуст, Streamlit выбрасывает StreamlitSecretNotFoundError
        pass
    return {"token": token, "repo": repo, "branch": branch}

def sync_file_and_notify(filepath, message="Update"):
    """Заглушка синхронизации с GitHub."""
    cfg = get_github_config()
    if not cfg["token"]:
        return False
    # При наличии валидного токена здесь может быть вызов GitHub API
    return True
