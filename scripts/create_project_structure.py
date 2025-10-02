#!/usr/bin/env python3
"""Bootstrap a GitHub Project V2 with milestones, epics, and tasks."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


GRAPHQL_URL = "https://api.github.com/graphql"
REST_BASE = "https://api.github.com"
USER_AGENT = "project-bootstrap-script/1.0"


class GitHubClient:
    """Minimal GitHub REST + GraphQL helper."""

    def __init__(self, token: str) -> None:
        self._token = token

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(GRAPHQL_URL, data=payload, method="POST")
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(request) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"GraphQL request failed: {exc.code} {exc.reason}: {message}"
            ) from exc
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    def rest(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not path.startswith("/"):
            raise ValueError(f"REST path must start with '/': {path}")
        url = f"{REST_BASE}{path}"
        data: Optional[bytes] = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method.upper())
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(request) as response:
                if response.status == 204:
                    return {}
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"REST {method} {path} failed: {exc.code} {exc.reason}: {message}"
            ) from exc


def load_hierarchy(path: pathlib.Path) -> Dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:  # noqa: PERF203 - clarity over micro-optimisation
        raise SystemExit(f"Failed to read hierarchy file '{path}': {exc}") from exc
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Hierarchy JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Hierarchy JSON must be an object with a 'milestones' array.")
    return data


def resolve_owner_id(client: GitHubClient, owner_login: str) -> str:
    query = """
    query($login: String!) {
      repositoryOwner(login: $login) {
        id
        login
        __typename
      }
    }
    """
    data = client.graphql(query, {"login": owner_login})
    owner = data.get("repositoryOwner")
    if not owner or not owner.get("id"):
        raise RuntimeError(f"Unable to resolve repository owner id for '{owner_login}'.")
    return owner["id"]


def create_project(client: GitHubClient, owner_id: str, title: str, description: Optional[str]) -> Dict[str, Any]:
    mutation = """
    mutation($ownerId: ID!, $title: String!) {
      createProjectV2(input: {ownerId: $ownerId, title: $title}) {
        projectV2 {
          id
          number
          title
          url
        }
      }
    }
    """
    data = client.graphql(mutation, {"ownerId": owner_id, "title": title})
    project = data["createProjectV2"]["projectV2"]
    if description:
        update = """
        mutation($projectId: ID!, $description: String!) {
          updateProjectV2(input: {projectId: $projectId, shortDescription: $description}) {
            projectV2 { id }
          }
        }
        """
        client.graphql(update, {"projectId": project["id"], "description": description})
    return project


def fetch_status_field(client: GitHubClient, project_id: str) -> Optional[Dict[str, Any]]:
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 20) {
            nodes {
              __typename
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    data = client.graphql(query, {"projectId": project_id})
    node = data.get("node")
    if not node:
        return None
    fields = node.get("fields", {}).get("nodes", [])
    for field in fields:
        if field.get("name") == "Status":
            for option in field.get("options", []):
                if option.get("name").lower() == "to do":
                    return {"field_id": field["id"], "option_id": option["id"]}
    return None


def add_issue_to_project(
    client: GitHubClient,
    project_id: str,
    issue_node_id: str,
) -> str:
    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = client.graphql(mutation, {"projectId": project_id, "contentId": issue_node_id})
    return data["addProjectV2ItemById"]["item"]["id"]


def set_status_value(
    client: GitHubClient,
    project_id: str,
    item_id: str,
    status_field: Dict[str, Any],
) -> None:
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(
        input: {
          projectId: $projectId,
          itemId: $itemId,
          fieldId: $fieldId,
          value: {singleSelectOptionId: $optionId}
        }
      ) {
        projectV2Item {
          id
        }
      }
    }
    """
    client.graphql(
        mutation,
        {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": status_field["field_id"],
            "optionId": status_field["option_id"],
        },
    )


def ensure_label_list(raw: Optional[Any], default: Optional[List[str]] = None) -> List[str]:
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return raw
    return default[:] if default else []


def create_milestone(
    client: GitHubClient,
    owner: str,
    repo: str,
    milestone: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"title": milestone.get("title", "Untitled Milestone")}
    if description := milestone.get("description"):
        payload["description"] = description
    if due_on := milestone.get("due_on"):
        payload["due_on"] = due_on
    response = client.rest("POST", f"/repos/{owner}/{repo}/milestones", payload)
    return response


def create_issue(
    client: GitHubClient,
    owner: str,
    repo: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    response = client.rest("POST", f"/repos/{owner}/{repo}/issues", payload)
    return response


def update_issue_body(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
) -> None:
    client.rest("PATCH", f"/repos/{owner}/{repo}/issues/{issue_number}", {"body": body})


def build_epic_body(original_body: str, tasks: List[Dict[str, Any]]) -> str:
    sections: List[str] = []
    if original_body:
        sections.append(original_body.strip())
    if tasks:
        lines = ["## Tasks"]
        for task in tasks:
            lines.append(f"- [ ] #{task['number']} {task['title']}")
        sections.append("\n".join(lines))
    return "\n\n".join(section for section in sections if section).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-title", required=True, help="Title for the new project board.")
    parser.add_argument("--project-description", default="", help="Optional project description.")
    parser.add_argument(
        "--hierarchy-file",
        required=True,
        help="Path to a JSON file describing milestones, epics, and tasks.",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN environment variable is required.")

    repo_env = os.environ.get("GITHUB_REPOSITORY")
    if not repo_env or "/" not in repo_env:
        raise SystemExit("GITHUB_REPOSITORY environment variable is malformed or missing.")
    owner, repo = repo_env.split("/", 1)

    hierarchy_path = pathlib.Path(args.hierarchy_file)
    hierarchy = load_hierarchy(hierarchy_path)
    milestones_data = hierarchy.get("milestones", [])
    if not isinstance(milestones_data, list):
        raise SystemExit("Hierarchy JSON 'milestones' key must be a list.")

    client = GitHubClient(token)
    owner_id = resolve_owner_id(client, owner)
    project = create_project(client, owner_id, args.project_title, args.project_description.strip())
    status_field = fetch_status_field(client, project["id"])

    summary: Dict[str, Any] = {
        "project": project,
        "milestones": [],
        "epics": [],
        "tasks": [],
    }

    for milestone_data in milestones_data:
        milestone_response = create_milestone(client, owner, repo, milestone_data)
        summary["milestones"].append(
            {
                "title": milestone_response.get("title"),
                "number": milestone_response.get("number"),
                "url": f"https://github.com/{owner}/{repo}/milestone/{milestone_response.get('number')}",
            }
        )
        milestone_number = milestone_response.get("number")

        epics = milestone_data.get("epics", [])
        if not isinstance(epics, list):
            continue
        for epic in epics:
            epic_title = epic.get("title", "Untitled Epic")
            epic_body = epic.get("body", "").strip()
            epic_labels = ensure_label_list(epic.get("labels"), ["type: epic"])
            epic_payload: Dict[str, Any] = {
                "title": epic_title,
                "body": epic_body,
                "labels": epic_labels,
            }
            if milestone_number is not None:
                epic_payload["milestone"] = milestone_number
            if assignees := epic.get("assignees"):
                epic_payload["assignees"] = assignees

            epic_issue = create_issue(client, owner, repo, epic_payload)
            summary["epics"].append(
                {
                    "title": epic_issue.get("title"),
                    "number": epic_issue.get("number"),
                    "url": epic_issue.get("html_url"),
                }
            )

            item_id = add_issue_to_project(client, project["id"], epic_issue["node_id"])
            if status_field:
                set_status_value(client, project["id"], item_id, status_field)

            tasks = epic.get("tasks", [])
            created_tasks: List[Dict[str, Any]] = []
            if isinstance(tasks, list):
                for task in tasks:
                    task_title = task.get("title", "Untitled Task")
                    task_body = task.get("body", "").strip()
                    task_labels = ensure_label_list(task.get("labels"), ["type: task"])
                    body_sections = [section for section in [task_body, f"Parent: #{epic_issue['number']}"] if section]
                    task_payload: Dict[str, Any] = {
                        "title": task_title,
                        "body": "\n\n".join(body_sections),
                        "labels": task_labels,
                    }
                    if milestone_number is not None:
                        task_payload["milestone"] = milestone_number
                    if assignees := task.get("assignees"):
                        task_payload["assignees"] = assignees

                    task_issue = create_issue(client, owner, repo, task_payload)
                    task_item_id = add_issue_to_project(client, project["id"], task_issue["node_id"])
                    if status_field:
                        set_status_value(client, project["id"], task_item_id, status_field)

                    created_tasks.append(
                        {
                            "title": task_issue.get("title"),
                            "number": task_issue.get("number"),
                            "url": task_issue.get("html_url"),
                        }
                    )
                    summary["tasks"].append(created_tasks[-1])

            updated_body = build_epic_body(epic_body, created_tasks)
            if updated_body:
                update_issue_body(client, owner, repo, epic_issue["number"], updated_body)

    output = json.dumps(summary, indent=2)
    print(output)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = ["### Project Bootstrap Summary", ""]
        lines.append(f"- Project: [{project['title']}]({project['url']})")
        if summary["milestones"]:
            lines.append("- Milestones:")
            for milestone in summary["milestones"]:
                title = milestone.get("title", "(untitled)")
                number = milestone.get("number")
                lines.append(
                    f"  - [{title}](https://github.com/{owner}/{repo}/milestone/{number})"
                )
        if summary["epics"]:
            lines.append("- Epics:")
            for epic in summary["epics"]:
                lines.append(f"  - [{epic['title']}]({epic['url']})")
        if summary["tasks"]:
            lines.append("- Tasks:")
            for task in summary["tasks"]:
                lines.append(f"  - [{task['title']}]({task['url']})")
        lines.append("")
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
            handle.write("\n")


if __name__ == "__main__":
    main()
