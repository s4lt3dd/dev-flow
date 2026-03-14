"""
Jira Exporter: publishes generated user stories to Jira via REST API v3.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib import response

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

class JiraExporter:
    """Export generated user stories to Jira as Story issues."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        story_points_field: str = "customfield_10016",
    ):
        """
        Args:
            base_url: Jira instance URL, e.g. https://yoursite.atlassian.net
            email: Atlassian account email used for authentication
            api_token: Jira API token (create at id.atlassian.com/manage-profile/security)
            project_key: Jira project key, e.g. "DEV"
            story_points_field: Custom field ID for story points.
                                Jira Cloud default is "customfield_10016".
        """
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.story_points_field = story_points_field
        self._auth = HTTPBasicAuth(email, api_token)
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._issues_url = f"{self.base_url}/rest/api/3/issue"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_story(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single Jira Story issue from a generated story dict.

        Returns a dict with 'jira_key', 'jira_id', and 'jira_url' on success.
        Raises requests.HTTPError on API failure.
        """
        payload = self._build_payload(story)
        response = requests.post(
            self._issues_url,
            json=payload,
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        if not response.ok:
            raise requests.HTTPError(
                f"{response.status_code}: {response.text}", response=response
            )           
        #response.raise_for_status()
        data = response.json()
        result = {
            "jira_key": data["key"],
            "jira_id": data["id"],
            "jira_url": f"{self.base_url}/browse/{data['key']}",
        }
        logger.info(f"Created Jira issue {result['jira_key']}: '{story['title']}'")
        return result

    def export_stories(self, stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Export a list of stories, continuing past individual failures.

        Returns one result dict per story with either Jira fields or an 'error' key.
        """
        results = []
        for story in stories:
            try:
                jira = self.export_story(story)
                results.append({"title": story["title"], **jira})
            except Exception as e:
                logger.error(f"Failed to export '{story['title']}' to Jira: {e}")
                results.append({"title": story["title"], "error": str(e)})
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, story: Dict[str, Any]) -> Dict[str, Any]:
        issue_type = story.get("issue_type", "Story")
        fields: Dict[str, Any] = {
            "project":     {"key": self.project_key},
            "summary":     story["title"],
            "description": self._build_description(story),
            "issuetype":   {"name": issue_type},
            "priority":    {"name": story["priority"]},
        }

        # Story points (Jira Cloud: customfield_10016; Scrum boards expose this)
        story_points = story.get("story_points")
        if story_points is not None:
            fields[self.story_points_field] = float(story_points)

        return {"fields": fields}

    def _build_description(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """Format description as Atlassian Document Format (ADF) for API v3."""
        ac_list_items = [
            {
                "type": "listItem",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": ac}],
                    }
                ],
            }
            for ac in story.get("acceptance_criteria", [])
        ]

        content = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": story.get("story", "")}],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Acceptance Criteria:",
                        "marks": [{"type": "strong"}],
                    }
                ],
            },
            {"type": "bulletList", "content": ac_list_items},
        ]

        # Append notes section when present
        notes = story.get("notes", "").strip() if story.get("notes") else ""
        if notes:
            content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Notes:", "marks": [{"type": "strong"}]},
                ],
            })
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": notes}],
            })

        return {"type": "doc", "version": 1, "content": content}
