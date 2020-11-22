import glob
import pathlib
import json  # type: ignore
import pytest  # type: ignore
from moto import mock_acm  # type: ignore
import boto3  # type: ignore


@pytest.fixture(scope="function")
def acm_client():
    mock = mock_acm()
    mock.start()
    acm_client = boto3.client("acm")

    for certificate_json in (
        "certificate1_pending.json",
        "certificate1_available.json",
        "certificate1_delete.json",
    ):
        with pytest.test_files[certificate_json].open() as certificate_file:
            certificate = json.loads(certificate_file.read())
            r = acm_client.request_certificate(**certificate)
            # Workaround moto's bug (Tags are not added): https://github.com/spulec/moto/issues/3377
            acm_client.add_tags_to_certificate(CertificateArn=r["CertificateArn"], Tags=certificate["Tags"])

    yield acm_client
    mock.stop()
