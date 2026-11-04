"""One-time AWS setup for Yorisoi (run with your own AWS credentials).

Creates:
  - DynamoDB table for reminders
  - SNS topic + email subscription for the family (confirm the email AWS sends!)
  - IAM role that EventBridge Scheduler uses to publish to SNS
Writes agent/settings.json and runtime-policy.json (permissions for the AgentCore runtime role).

Usage:
  python scripts/setup_aws.py --email family@example.com
"""
import argparse
import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "agent" / "settings.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True, help="family email that receives alerts")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--table", default="yorisoi-reminders")
    p.add_argument("--user-name", default="田中さん")
    p.add_argument("--escalation-minutes", type=int, default=30)
    a = p.parse_args()

    account = boto3.client("sts").get_caller_identity()["Account"]
    ddb = boto3.client("dynamodb", region_name=a.region)
    sns = boto3.client("sns", region_name=a.region)
    iam = boto3.client("iam")

    # 1. DynamoDB
    try:
        ddb.create_table(
            TableName=a.table,
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"},
                       {"AttributeName": "reminder_id", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"},
                                  {"AttributeName": "reminder_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Creating table {a.table} ...")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            raise
        print(f"Table {a.table} already exists")
    ddb.get_waiter("table_exists").wait(TableName=a.table)
    table_arn = f"arn:aws:dynamodb:{a.region}:{account}:table/{a.table}"

    # 2. SNS topic + email subscription
    topic_arn = sns.create_topic(Name="yorisoi-family-alerts")["TopicArn"]
    sns.set_topic_attributes(TopicArn=topic_arn, AttributeName="DisplayName", AttributeValue="Yorisoi Care Alerts")
    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]
    if not any(s["Endpoint"] == a.email for s in subs):
        sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=a.email)
        print(f"Subscribed {a.email} -> CHECK THAT INBOX AND CLICK 'Confirm subscription'")
    else:
        print(f"{a.email} already subscribed")

    # 3. IAM role for EventBridge Scheduler -> SNS
    role_name = "yorisoi-scheduler-role"
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "scheduler.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": account}},
        }],
    }
    try:
        role_arn = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        print(f"Created role {role_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        print(f"Role {role_name} already exists")
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="publish-family-alerts",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "sns:Publish", "Resource": topic_arn}],
        }),
    )

    # 4. settings.json (keeps existing keys such as agent_runtime_arn)
    settings = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    settings.update({
        "aws_region": a.region,
        "table_name": a.table,
        "sns_topic_arn": topic_arn,
        "scheduler_role_arn": role_arn,
        "user_name": a.user_name,
        "escalation_minutes": a.escalation_minutes,
    })
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {SETTINGS}")

    # 5. Permissions the AgentCore runtime role needs (attach after deploy)
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow",
             "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"],
             "Resource": table_arn},
            {"Effect": "Allow",
             "Action": ["scheduler:CreateSchedule", "scheduler:DeleteSchedule"],
             "Resource": f"arn:aws:scheduler:{a.region}:{account}:schedule/default/yorisoi-*"},
            {"Effect": "Allow", "Action": "iam:PassRole", "Resource": role_arn,
             "Condition": {"StringEquals": {"iam:PassedToService": "scheduler.amazonaws.com"}}},
            {"Effect": "Allow", "Action": "sns:Publish", "Resource": topic_arn},
        ],
    }
    out = ROOT / "runtime-policy.json"
    out.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    print(f"Wrote {out} (attach it to the AgentCore runtime role after deploying, see README)")


if __name__ == "__main__":
    main()
