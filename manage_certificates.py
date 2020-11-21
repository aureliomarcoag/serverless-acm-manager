from typing import List, Generator
import os
import uuid
import boto3
import certifier


s3_client = boto3.resource("s3")
actions = certifier.actions()


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


def handler(event, context):
    """
    Main function handler, parse S3 events for requesting and deleting certificates
    """
    try:
        (
            delete_certificates,
            create_certificates,
            failed_certificates,
        ) = certifier.certifier.get_certificates_from_s3_event(event)
        for certificate in delete_certificates:
            actions.mark_for_deletion(actions.query(identifier=certificate[2]))
        for certificate in create_certificates:
            bucket, key, identifier = certificate
            domains = read_domains_from_file(next(get_file_from_s3(bucket, key)))
            actions.request_certificate(identifier, domains)
        for certificate in failed_certificates:
            print("Failed to create certificate from s3://{}/{} with the following reason: {}".format(*certificate))

        print("Delete: {}, Create: {}".format(str(delete_certificates), str(create_certificates)))
    except Exception as exception:
        print("Failed to parse S3 event: " + str(exception))


if __name__ == "__main__":
    import sys
    import json

    handler(json.loads(sys.argv[1]), None)
