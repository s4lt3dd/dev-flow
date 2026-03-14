import os
from dotenv import load_dotenv

load_dotenv()  # reads .env into os.environ

def get_jira_config() -> dict:
    required = {
        "base_url":    os.getenv("JIRA_BASE_URL"),
        "email":       os.getenv("JIRA_EMAIL"),
        "api_token":   os.getenv("JIRA_API_TOKEN"),
        "project_key": os.getenv("JIRA_PROJECT_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required Jira config: {', '.join(missing)}\n"
            "Check your .env file or environment variables."
        )
    return required