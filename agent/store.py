"""Reminder storage and family alerts.

- DynamoDB stores reminders (PK user_id, SK reminder_id).
- For medicine reminders, an EventBridge Scheduler one-time schedule is created
  at (due time + ESCALATION_MINUTES). It publishes straight to SNS -> family email.
- When the senior confirms ("飲みました"), the schedule is deleted, so the alert
  only fires if the dose was NOT confirmed. No Lambda needed.
"""
import uuid
import json
import uuid
from datetime import datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import config

_ddb = boto3.resource("dynamodb", region_name=config.AWS_REGION)
_table = _ddb.Table(config.TABLE_NAME)
_scheduler = boto3.client("scheduler", region_name=config.AWS_REGION)
_sns = boto3.client("sns", region_name=config.AWS_REGION)


def now() -> datetime:
    return datetime.now(config.TZ)


def parse_time(value: str) -> datetime:
    """Parse 'YYYY-MM-DDTHH:MM' (Japan time if no timezone given)."""
    dt = datetime.fromisoformat(value.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.TZ)
    return dt.astimezone(config.TZ)


def _schedule_name(reminder_id: str) -> str:
    return f"yorisoi-{config.USER_ID}-{reminder_id}"[:64]


def _create_escalation(item: dict, due_at: datetime) -> str | None:
    if not (config.SNS_TOPIC_ARN and config.SCHEDULER_ROLE_ARN):
        return None
    if due_at < now() - timedelta(minutes=1):  # reminder already in the past
        return None
    fire_at = max(due_at + timedelta(minutes=config.ESCALATION_MINUTES), now() + timedelta(minutes=1))
    message = (
        "【日本語】\n"
        f"{config.USER_NAME}が、お薬を飲んだ確認をまだしていません。\n\n"
        f"　お薬：{item['title']}\n"
        f"　予定：{due_at.month}月{due_at.day}日 {due_at:%H:%M}\n\n"
        "お電話などで、ご様子を確認してください。\n\n"
        "【English】\n"
        f"{config.USER_NAME} has not confirmed taking their medicine yet.\n\n"
        f"  Medicine: {item['title']}\n"
        f"  Scheduled: {due_at:%b %d, %H:%M} (JST)\n\n"
        "Please give them a call or check on them.\n\n"
        "— よりそい / Yorisoi"
    )
    subject = f"【よりそい】お薬の確認がありません / Dose not confirmed: {config.USER_NAME}"
    name = _schedule_name(item["reminder_id"])
    _scheduler.create_schedule(
        Name=name,
        GroupName=config.SCHEDULE_GROUP,
        ScheduleExpression=f"at({fire_at:%Y-%m-%dT%H:%M:%S})",
        ScheduleExpressionTimezone="Asia/Tokyo",
        FlexibleTimeWindow={"Mode": "OFF"},
        # Universal target: calls SNS Publish with our own Subject
        # (the plain SNS target only sends a Message, so the subject would be "AWS Notification Message").
        Target={
            "Arn": "arn:aws:scheduler:::aws-sdk:sns:publish",
            "RoleArn": config.SCHEDULER_ROLE_ARN,
            "Input": json.dumps(
                {"TopicArn": config.SNS_TOPIC_ARN, "Subject": subject[:99], "Message": message},
                ensure_ascii=False,
            ),
        },
        ActionAfterCompletion="DELETE",
    )
    return name


def _delete_escalation(item: dict) -> None:
    name = item.get("escalation_schedule")
    if not name:
        return
    try:
        _scheduler.delete_schedule(Name=name, GroupName=config.SCHEDULE_GROUP)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise


def add_reminder(title: str, kind: str, due_at: datetime, note: str = "") -> dict:
    item = {
        "user_id": config.USER_ID,
        "reminder_id": uuid.uuid4().hex[:8],
        "title": title,
        "kind": kind,
        "due_at": due_at.isoformat(timespec="minutes"),
        "status": "pending",
        "note": note,
        "created_at": now().isoformat(timespec="seconds"),
    }
    if kind == "medicine":
        name = _create_escalation(item, due_at)
        if name:
            item["escalation_schedule"] = name
    _table.put_item(Item=item)
    return item


def get_reminder(reminder_id: str) -> dict | None:
    return _table.get_item(Key={"user_id": config.USER_ID, "reminder_id": reminder_id}).get("Item")


def _set_status(reminder_id: str, status: str) -> dict | None:
    item = get_reminder(reminder_id)
    if not item:
        return None
    _delete_escalation(item)
    _table.update_item(
        Key={"user_id": config.USER_ID, "reminder_id": reminder_id},
        UpdateExpression="SET #s = :s, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":u": now().isoformat(timespec="seconds")},
    )
    item["status"] = status
    return item


def complete(reminder_id: str) -> dict | None:
    return _set_status(reminder_id, "done")


def cancel(reminder_id: str) -> dict | None:
    return _set_status(reminder_id, "cancelled")


def list_reminders(include_done: bool = False) -> list[dict]:
    items = _table.query(KeyConditionExpression=Key("user_id").eq(config.USER_ID))["Items"]
    if not include_done:
        items = [i for i in items if i["status"] == "pending"]
    return sorted(items, key=lambda i: i["due_at"])


def due_reminders() -> list[dict]:
    """Pending reminders whose time has come (used by the UI to ring)."""
    t = now()
    return [i for i in list_reminders() if parse_time(i["due_at"]) <= t]


def notify_family(message: str) -> str:
    if config.DRY_RUN:
        return "dry-run: family message not sent"
    if not config.SNS_TOPIC_ARN:
        return "family contact is not configured"
    _sns.publish(
        TopicArn=config.SNS_TOPIC_ARN,
        Subject=f"【よりそい】{config.USER_NAME}からのお知らせ / Message from {config.USER_NAME}"[:99],
        Message=(
            "【日本語】\n"
            f"{config.USER_NAME}から、よりそいを通じてお知らせです。\n\n"
            f"{message}\n\n"
            "【English】\n"
            f"{config.USER_NAME} asked Yorisoi to send you this message (Japanese above).\n"
            "Please give them a call when you can.\n\n"
            "— よりそい / Yorisoi"
        ),
    )
    return "sent"
