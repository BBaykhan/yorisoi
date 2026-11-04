"""Japanese text-to-speech with Amazon Polly."""
import re

import boto3
from botocore.exceptions import ClientError

import config

_polly = boto3.client("polly", region_name=config.AWS_REGION)
# Tried in order: neural voices first, standard voice as a fallback.
_VOICES = [("Kazuha", "neural"), ("Takumi", "neural"), ("Mizuki", "standard")]


def _clean(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*#|_`>\[\]]", "", text)
    return text.strip()[:2500]


def speak(text: str) -> bytes | None:
    text = _clean(text)
    if not text:
        return None
    for voice, engine in _VOICES:
        try:
            return _polly.synthesize_speech(
                Text=text, OutputFormat="mp3", VoiceId=voice, Engine=engine, LanguageCode="ja-JP"
            )["AudioStream"].read()
        except ClientError:
            continue
    return None
