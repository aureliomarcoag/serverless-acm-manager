import os
import re
import uuid
from typing import List, Generator, Tuple, Dict
import boto3  # type: ignore
from certifier import certifier

actions = certifier.actions()
s3_client = boto3.resource("s3")


def get_certificates_from_s3_event(
    event: Dict,
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    """
    Returns a tuple containing three lists. The first one is a list of certificates to delete,
    the second is a list of certificates to create, and the third one contains certificates that failed a validation.
    Each create and delete list item is a tuple formed by the s3 bucket name, the key of the object in the bucket
    and the key stripped of file extensions (up to the first dot).
    The third element of tuples in the list of failed items is the reason for the failure instead of the object key stripped of extensions.
    The following validation is performed:
    * Make sure the S3 key only contains letters, numbers and the characters .-_ to make sure it can be used as the name of a parameter in Parameter Store.
    Example of a create list:
    [("my_bucket", "key/to.my/object.first.txt", "key/to/object")]
    Example of a failure list:
    [("my_bucket", "key/to.my/object.first.txt", "the S3 object key contains invalid characters")]
    """
    if "Records" not in event:
        raise KeyError("'Records' key not found in event object")

    name_pattern = re.compile(r"([A-Za-z0-9]|-|_|\.|/)+")
    delete_certificates: List[Tuple[str, str, str]] = []
    create_certificates: List[Tuple[str, str, str]] = []
    failed_certificates: List[Tuple[str, str, str]] = []

    for record in event["Records"]:
        s3_data: Dict = record["s3"]
        certificate_file_data: Tuple[str, str] = (
            s3_data["bucket"]["name"],
            s3_data["object"]["key"],
        )

        failed_reason = ""
        if certificate_file_data[1][-1] == "/":
            failed_reason += f"Ignoring S3 folder object: 's3://{'/'.join(certificate_file_data)}'. "

        if not name_pattern.fullmatch(certificate_file_data[1]):
            failed_reason += f"The S3 object key '{certificate_file_data[1]}' is not a valid parameter name for AWS Parameter Store (it does not match '{name_pattern.pattern}'). "

        if failed_reason:
            failed_certificates.append(certificate_file_data + (failed_reason,))
            continue

        split_key = certificate_file_data[1].split("/")
        key_stripped_extension = "/".join(split_key[:-1] + [split_key[-1].split(".")[0]])

        if record["eventName"].startswith("ObjectCreated"):
            create_certificates.append(certificate_file_data + (key_stripped_extension,))
        if record["eventName"].startswith("ObjectRemoved"):
            delete_certificates.append(certificate_file_data + (key_stripped_extension,))

    return delete_certificates, create_certificates, failed_certificates


def get_file_from_s3(bucket: str, key: str) -> Generator[str, None, None]:
    """
    Yields the local path to the downloaded file and then deletes it
    """
    file_path: str = "/tmp/{uuid.uuid4()}"
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
    ) = get_certificates_from_s3_event(event)
    for certificate in certificates_to_delete:
        actions.mark_for_deletion(actions.query(identifier=certificate[2]))
    for certificate in certificates_to_create:
        bucket, key, identifier = certificate
        domains = read_domains_from_file(next(get_file_from_s3(bucket, key)))
        actions.request_certificate(identifier, domains)
    for certificate in certificates_failed:
        print(
            f"Failed to create certificate from s3://{'/'.join(certificate[:2])} with the following reason: {certificate[2]}"
        )

    print("Delete: {certificates_to_delete}, Create: {certificates_to_create}")


def transition_certificates(event, context):
    """
    Handler for lambda to transition certificates
    """
    certificates = actions.query(with_acm_state=True)
    for certificate in certificates:
        if certificate.state == certifier.States.PENDING:
            if certificate.acm_state == "FAILED":
                print("Failed to validate certificate, retrying: {certificate}")
                actions.retry_failed(certificate)
            if certificate.acm_state == "ISSUED":
                print("Transitioning certificate to available state: {certificate}")
                actions.transition_to_available([certificate])
