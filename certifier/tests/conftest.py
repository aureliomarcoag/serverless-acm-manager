import pytest  # type: ignore
from moto import mock_acm  # type: ignore
import boto3  # type: ignore
import json  # type: ignore


def reload_certificates(acm_client):
    for certificate in acm_client.list_certificates()["CertificateSummaryList"]:
        acm_client.delete_certificate(CertificateArn=certificate["CertificateArn"])

    for certificate_json in (
        "files/certificate1_pending.json",
        "files/certificate1_available.json",
        "files/certificate1_delete.json",
    ):
        with open(certificate_json) as certificate_file:
            certificate = json.loads(certificate_file.read())
            r = acm_client.request_certificate(**certificate)
            # Workaround moto's bug (Tags are not added): https://github.com/spulec/moto/issues/3377
            acm_client.add_tags_to_certificate(CertificateArn=r["CertificateArn"], Tags=certificate["Tags"])


@pytest.fixture(scope="module")
def acm_client():
    mock = mock_acm()
    mock.start()
    acm_client = boto3.client("acm")
    reload_certificates(acm_client)
    yield acm_client
    mock.stop()
