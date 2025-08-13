from flask import Flask, request, jsonify
import requests
import json
import traceback
from datetime import datetime
import os

app = Flask(__name__)

# === Configuration ===
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
ASANA_PROJECT_ID = os.getenv("ASANA_PROJECT_ID")

def log_message(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def extract_paragraph_text(paragraph):
    try:
        if "content" in paragraph:
            text_parts = []
            for item in paragraph["content"]:
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(item["text"])
            return "".join(text_parts)
        return ""
    except Exception:
        return ""

def extract_text_from_adf(adf_content):
    try:
        if isinstance(adf_content, dict) and "content" in adf_content:
            text_parts = []
            for content_item in adf_content["content"]:
                if content_item.get("type") == "paragraph":
                    paragraph_text = extract_paragraph_text(content_item)
                    if paragraph_text:
                        text_parts.append(paragraph_text)
            return "\n".join(text_parts)
        return str(adf_content)
    except Exception as e:
        log_message(f"Error extracting text from ADF: {str(e)}", "WARN")
        return str(adf_content)

def create_asana_task(task_name, task_notes):
    try:
        headers = {
            "Authorization": f"Bearer {ASANA_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "data": {
                "name": task_name,
                "notes": task_notes,
                "projects": [ASANA_PROJECT_ID]
            }
        }

        log_message("Sending request to Asana API")
        response = requests.post(
            "https://app.asana.com/api/1.0/tasks",
            json=payload,
            headers=headers,
            timeout=30
        )

        log_message(f"Asana API response status: {response.status_code}")

        if response.status_code == 201:
            task_data = response.json()
            task_gid = task_data.get("data", {}).get("gid", "Unknown")
            return {
                "status": "success",
                "message": "Task created successfully in Asana",
                "task_id": task_gid,
                "task_name": task_name,
                "asana_url": f"https://app.asana.com/0/{ASANA_PROJECT_ID}/{task_gid}"
            }
        else:
            error_msg = f"Asana API Error: {response.status_code} - {response.text}"
            log_message(error_msg, "ERROR")
            return {
                "status": "error",
                "message": error_msg,
                "error_type": "asana_api",
                "status_code": response.status_code
            }

    except requests.RequestException as e:
        error_msg = f"Network error while calling Asana API: {str(e)}"
        log_message(error_msg, "ERROR")
        return {"status": "error", "message": error_msg, "error_type": "network"}
    except Exception as e:
        error_msg = f"Unexpected error creating Asana task: {str(e)}"
        log_message(error_msg, "ERROR")
        return {"status": "error", "message": error_msg, "error_type": "task_creation"}

def create_asana_task_from_jira_webhook(data):
    try:
        log_message("Starting Jira to Asana sync process")

        issue = data.get("issue", {})
        jira_key = issue.get("key", "UNKNOWN")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "No Title")
        description = fields.get("description", "")

        if isinstance(description, dict):
            description_text = extract_text_from_adf(description)
        else:
            description_text = str(description) if description else ""

        log_message(f"Processing Jira issue: {jira_key} - {summary}")

        asana_task_name = f"[{jira_key}] {summary}"
        asana_task_notes = f"Jira Issue: {jira_key}\nOriginal Summary: {summary}\n\n"
        if description_text:
            asana_task_notes += f"Description:\n{description_text}"

        result = create_asana_task(asana_task_name, asana_task_notes)
        if result["status"] == "success":
            log_message(f"Successfully created Asana task for {jira_key}")
        return result

    except Exception as e:
        error_msg = f"Error processing webhook data: {str(e)}"
        log_message(error_msg, "ERROR")
        log_message(traceback.format_exc(), "ERROR")
        return {"status": "error", "message": error_msg, "error_type": "processing"}

@app.route('/jira-webhook', methods=['POST'])
def jira_webhook():
    if not request.is_json:
        return jsonify({"status": "error", "message": "Expected JSON data"}), 400

    data = request.get_json()
    result = create_asana_task_from_jira_webhook(data)
    return jsonify(result)

if __name__ == "__main__":
    print("Starting Jira to Asana sync Flask API...")
    app.run(host="0.0.0.0", port=5000)
