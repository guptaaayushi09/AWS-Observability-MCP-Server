"""boto3 client construction, centralized.

Clients are built on demand (not at import time) so that test mocks such as moto can
intercept the calls, and so a single place controls region and endpoint configuration.
"""

from __future__ import annotations

import os

import boto3

DEFAULT_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


def get_client(service: str, region: str | None = None):
    """Return a boto3 client for the given AWS service.

    An optional ``AWS_ENDPOINT_URL`` env var points every client at a local emulator
    (LocalStack) for end-to-end testing without touching real AWS.
    """
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or None
    return boto3.client(
        service,
        region_name=region or DEFAULT_REGION,
        endpoint_url=endpoint_url,
    )
