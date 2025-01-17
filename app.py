import os
import requests
from flask import Flask, request, abort
import logging
import urllib3

app = Flask(__name__)

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Environment variables for configuration
MATTERMOST_WEBHOOK_URL = os.getenv("MATTERMOST_WEBHOOK_URL")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

if not MATTERMOST_WEBHOOK_URL:
    raise EnvironmentError("MATTERMOST_WEBHOOK_URL is not set.")


def extract_jira_domain(issue_self_url):
    """Extract the JIRA domain from the issue's self URL."""
    if not issue_self_url:
        raise ValueError("Issue self URL is missing in the webhook payload.")
    return "/".join(issue_self_url.split("/")[:3])  # Extract the base URL


def parse_comment_data(comment, is_update=False):
    """Extract relevant comment data for `comment_created` and `comment_updated` events."""
    comment_body = comment.get("body", "No comment provided")
    author_field = "updateAuthor" if is_update else "author"
    comment_author = comment.get(author_field, {})
    comment_author_display_name = comment_author.get("displayName", "Unknown user")
    comment_avatar_url = comment_author.get("avatarUrls", {}).get("48x48", "")

    prefix = "Comment updated" if is_update else "New comment"
    return {
        "text": f"{prefix}: \n> {comment_body}",
        "username": f"{comment_author_display_name} (from jira-bot)",
        "icon_url": comment_avatar_url,
    }


def format_jira_message(data):
    """Format the incoming JIRA webhook data into a readable message for Mattermost."""
    webhook_event = data.get("webhookEvent", "Unknown event")
    issue = data.get("issue", {})
    issue_key = issue.get("key", "N/A")
    issue_summary = issue.get("fields", {}).get("summary", "No summary provided")
    issue_self = issue.get("self", "")
    jira_domain = "/".join(issue_self.split("/")[:3]) if issue_self else ""
    issue_url = f"{jira_domain}/browse/{issue_key}" if jira_domain and issue_key != "N/A" else ""
    user = data.get("user", {})
    display_name = user.get("displayName", "Unknown user")
    avatar_url = user.get("avatarUrls", {}).get("48x48", "")

    # Default message payload
    message_payload = {
        "text": f"Unhandled event: {webhook_event}",
        "username": f"{display_name} (from jira-bot)",
        "icon_url": avatar_url,
    }

    # Handle issue created
    if webhook_event == "jira:issue_created":
        message_payload["text"] = f"New issue: [{issue_key}]({issue_url}) - {issue_summary}"

    # Handle issue updated
    elif webhook_event == "jira:issue_updated":
        changelog = data.get("changelog", {}).get("items", [])
        changes = []

        for change in changelog:
            field = change["field"]
            from_value = change.get("fromString", "None")
            to_value = change.get("toString", "None")

            changes.append(f"{field}: {from_value} ➡ {to_value}")

        changes_str = "\n".join(changes)
        message_payload["text"] = (
            f"Updated: [{issue_key}]({issue_url}) - {issue_summary}\n{changes_str}"
        )

    # Handle comment created
    elif webhook_event == "comment_created":
        comment = data.get("comment", {})
        message_payload = parse_comment_data(comment, is_update=False)

    # Handle comment updated
    elif webhook_event == "comment_updated":
        comment = data.get("comment", {})
        message_payload = parse_comment_data(comment, is_update=True)

    return message_payload


@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def handle_jira_webhook(path):
    """Handle incoming JIRA webhooks and send formatted messages to Mattermost."""
    data = request.json
    if not data:
        abort(400, description="No data received")

    try:
        message_payload = format_jira_message(data)

        # Append the incoming path to the Mattermost Webhook URL
        dynamic_webhook_url = f"{MATTERMOST_WEBHOOK_URL}/{path}"

        # Debug log to see what is being sent to Mattermost
        logging.debug("Sending payload to Mattermost (%s): %s", dynamic_webhook_url, message_payload)

        response = requests.post(
            dynamic_webhook_url,
            json=message_payload,
            verify=False  # This disables SSL verification for development
        )

        if response.status_code != 200:
            logging.error(
                "Failed to send message to Mattermost: %s", response.text, exc_info=True
            )
            # Return Mattermost's HTTP status code and response text
            return response.text, response.status_code
    except Exception as e:
        logging.error("Error processing webhook: %s", str(e), exc_info=True)
        abort(500, description=f"Error processing webhook: {str(e)}")

    return "Message sent to Mattermost", 200


if __name__ == '__main__':
    from waitress import serve
    serve(app, host=HOST, port=PORT)
