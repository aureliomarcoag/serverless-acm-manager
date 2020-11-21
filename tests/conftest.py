import pytest  # type: ignore
from moto import mock_acm  # type: ignore
import boto3  # type: ignore


@pytest.fixture(scope="function")
def acm_client():
    mock = mock_acm()
    mock.start()
    acm_client = boto3.client("acm")
    yield acm_client
    mock.stop()
