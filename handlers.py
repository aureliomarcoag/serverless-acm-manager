import os
import uuid
from typing import List, Generator
import boto3  # type: ignore
import certifier

actions = certifier.actions()
s3_client = boto3.resource("s3")


def get_file_from_s3(bucket: str, key: str) -> Generator[str, None, None]:
    """
    Yields the local path to the downloaded file and then deletes it
    """
    file_path: str = "/tmp/{}".format(str(uuid.uuid4()))
    s3_client.Bucket(bucket).download_file(key, file_path)
    yield file_path
    os.remove(file_path)


def read_domains_from_file(file_path: str) -> List[str]:
    """
    Returns a list of domains that are defined one per line on the specified file path
    """
    domains: List[str] = []
    with open(file_path) as domains_file:
        while (domain_line := domains_file.readline()) :
            domains.append(domain_line.strip("\n").strip(" "))
    return domains


def delete_certificates(event, context):
    """
    Handler for lambda to delete certificates
    """
    actions.delete(actions.query(state=certifier.States.MARKED_FOR_DELETION))


def manage_certificates(event, context):
    """
    Handler for lambda to manage certificates
    """
    (
        certificates_to_delete,
        certificates_to_create,
        certificates_failed,
    ) = certifier.certifier.get_certificates_from_s3_event(event)
    for certificate in certificates_to_delete:
        actions.mark_for_deletion(actions.query(identifier=certificate[2]))
    for certificate in certificates_to_create:
        bucket, key, identifier = certificate
        domains = read_domains_from_file(next(get_file_from_s3(bucket, key)))
        actions.request_certificate(identifier, domains)
    for certificate in certificates_failed:
        print("Failed to create certificate from s3://{}/{} with the following reason: {}".format(*certificate))

    print("Delete: {}, Create: {}".format(str(certificates_to_delete), str(certificates_to_create)))


def transition_certificates(event, context):
    """
    Handler for lambda to transition certificates
    """
    certificates = actions.query(with_acm_state=True)
    for certificate in certificates:
        if certificate.state == certifier.States.PENDING:
            if certificate.acm_state == "FAILED":
                print("Failed to validate certificate, retrying: {}".format(str(certificate)))
                actions.retry_failed(certificate)
            if certificate.acm_state == "ISSUED":
                print("Transitioning certificate to available state: {}".format(str(certificate)))
                actions.transition_to_available([certificate])
