"""Settings for Yorisoi.

Values come from environment variables first (UPPER_CASE names),
then from agent/settings.json (written by scripts/setup_aws.py).
settings.json is git-ignored because it contains your account ARNs and email.
"""
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

_SETTINGS_FILE = Path(__file__).with_name("settings.json")
_file = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")) if _SETTINGS_FILE.exists() else {}


def _get(key: str, default=None):
    return os.environ.get(key.upper(), _file.get(key, default))


AWS_REGION = _get("aws_region", "us-east-1")
TABLE_NAME = _get("table_name", "yorisoi-reminders")
SNS_TOPIC_ARN = _get("sns_topic_arn")            # family alert topic (email)
SCHEDULER_ROLE_ARN = _get("scheduler_role_arn")  # role EventBridge Scheduler uses to publish to SNS
SCHEDULE_GROUP = _get("schedule_group", "default")
AGENT_RUNTIME_ARN = _get("agent_runtime_arn")    # set after `agentcore deploy`; empty = run agent locally
AGENT_QUALIFIER = _get("agent_qualifier", "DEFAULT")
MODEL_ID = _get("model_id")                      # None = Strands default Bedrock model

USER_ID = _get("user_id", "tanaka")
USER_NAME = _get("user_name", "田中さん")

# Minutes after a medicine reminder before the family is alerted.
# Use 1 or 2 while recording the demo video.
ESCALATION_MINUTES = int(_get("escalation_minutes", 30))

# DRY_RUN=1 -> never send real emails (used by evals)
DRY_RUN = str(_get("dry_run", "0")) == "1"

TZ = ZoneInfo("Asia/Tokyo")
