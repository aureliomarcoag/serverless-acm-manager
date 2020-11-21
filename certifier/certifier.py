#!/usr/bin/env python3
import string
import random
import re
from enum import Enum
from typing import List, Tuple, Dict
import boto3  # type: ignore

# Test AVAILABLE certificate status after 1min in moto:
# https://github.com/spulec/moto/blob/master/moto/acm/models.py#L339


class Tags(Enum):
    """
    Enum representing the "Key" parts of tags created by certifier in ACM
    """

    IDENTIFIER: str = "certifier_id"
    STATE: str = "certifier_state"


class States(Enum):
    """
    Enum representing each state "Value" for the tag with the "Key" Tags.STATE in ACM
    """

    MARKED_FOR_DELETION: str = "certifier_delete"
    PENDING: str = "certifier_pending"
    AVAILABLE: str = "certifier_available"
    ANY: str = "_"


class Certificate:
    """
    A certificate object created based on data from ACM
    """

    def __init__(
        self, identifier: str, arn: str, state: States, records: List[Tuple[str, str]] = None, acm_state: str = None
    ) -> None:
        self.identifier = identifier
        self.arn = arn
        self.state = state
        self.records = records if records is not None else []
        self.acm_state = acm_state

    def __repr__(self):
        return "{}; {}; {}; {}; {} records;".format(
            self.identifier, self.state, self.acm_state, self.arn, len(self.records)
        )


class actions:
    """
    Actions represent operations that can be performed on a certificate or group of certificates
    """

    def __init__(self):
        self.acm_client = boto3.client("acm")
        self.ssm_client = boto3.client("ssm")

    def _list_certificates(self):
        """
        Runs list_certificates() however many api calls are necessary to retrieve all existing ACM certificates
        """
        all_raw_certificates: List = []
        while True:
            list_certificates_response: Dict = self.acm_client.list_certificates()
            all_raw_certificates.extend(list_certificates_response["CertificateSummaryList"])
            if "NextToken" not in list_certificates_response:
                break
        return all_raw_certificates

    def _get_acm_state(self, certificate: Certificate) -> str:
        """
        Uses the ARN of the certificate argument to query ACM for its status, which could be
        FAILED, ISSUED or PENDING_VALIDATION
        We refer to at as acm_state to be complient with the cetifier "state" naming.
        """
        return self.acm_client.describe_certificate(CertificateArn=certificate.arn)["Certificate"]["Status"]

    def _raw_certificates_to_objects(
        self,
        raw_certificates: List[Dict],
    ) -> List[Certificate]:
        """
        Converts a list of raw certificates as returned by a list_certitificates API call
        to a list of certifier.Certificate objects, ignoring certificates that do not contain both the
        certifier Tags.IDENTIFIER and Tags.STATE tags
        """
        certificates: List[Certificate] = []
        for raw_certificate in raw_certificates:
            raw_tags = self.acm_client.list_tags_for_certificate(CertificateArn=raw_certificate["CertificateArn"])[
                "Tags"
            ]
            tags: Dict[Tags, str] = {}
            for tag in raw_tags:
                try:
                    tags.update({Tags(tag["Key"]): tag["Value"]})
                except ValueError:
                    print("Ignoring unknown tag {}".format(tag["Key"]))

                if Tags.IDENTIFIER in tags and Tags.STATE in tags:
                    certificate = Certificate(
                        tags[Tags.IDENTIFIER],
                        raw_certificate["CertificateArn"],
                        States(tags[Tags.STATE]),
                    )

                    certificates.append(certificate)
        return certificates

    def query(
        self, identifier: str = None, state: States = States.ANY, with_records=False, with_acm_state: bool = False
    ) -> List[Certificate]:
        """
        Retrieves all ACM certificates and filters for the ones managed by certifier.
        More narrowed-down results can be obtained by filtering only for a specific
        identifier, specific state or both when 'identifier' and 'state' arguments are specified.
        """
        all_certificates: List[Certificate] = self._raw_certificates_to_objects(self._list_certificates())

        result_set: List[Certificate] = []
        for certificate in all_certificates:
            if identifier is None or identifier == certificate.identifier:
                if state == States.ANY or state == certificate.state:
                    result_set.append(certificate)
                    if with_records:
                        certificate.records = self._get_records(certificate.arn)
                    if with_acm_state:
                        certificate.acm_state = self._get_acm_state(certificate)
        return result_set

    def _get_records(self, certificate_arn) -> List[Tuple[str, str]]:
        """
        Returns a list of tuples containing (domain_validation_name, domain_validation_value)
        all of which are CNAMEs
        """
        certificate_data = self.acm_client.describe_certificate(CertificateArn=certificate_arn)["Certificate"]
        domain_validation_options = (
            [] if "DomainValidationOptions" not in certificate_data else certificate_data["DomainValidationOptions"]
        )

        return [
            (option["ResourceRecord"]["Name"], option["ResourceRecord"]["Value"])
            for option in domain_validation_options
        ]

    def mark_for_deletion(self, certificates: List[Certificate]) -> None:
        """
        Applies the certifier state States.MARKED_FOR_DELETION to a list of certificates
        by updating the tag Tags.STATE in ACM
        """
        for certificate in certificates:
            self.acm_client.add_tags_to_certificate(
                CertificateArn=certificate.arn,
                Tags=({"Key": Tags.STATE.value, "Value": States.MARKED_FOR_DELETION.value},),
            )

    def _delete_ssm_parameter(self, certificate):
        ssm_parameter_name = "/certifier/{}".format(certificate.identifier)
        ssm_parameter = self.ssm_client.get_parameter(Name=ssm_parameter_name)
        if "Parameter" in ssm_parameter and certificate.arn == ssm_paramter["Parameter"]["Value"]:
            self.ssm_client.delete_parameter(ssm_parameter_name)

    def delete(self, certificates: List[Certificate]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Delete a list of certificates in ACM, returning a tuple
        with a list of successful deletions and a list of failed deletions.
        """
        success: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        for certificate in certificates:
            try:
                self.acm_client.delete_certificate(CertificateArn=certificate.arn)
                success.append({certificate.arn: "Certificate deleted."})
                if certificate.state == States.AVAILABLE:
                    self._delete_ssm_parameter(certificate)
            except self.acm_client.exceptions.ResourceNotFoundException:
                success.append({certificate.arn: "Certificate not found when attempting to delete."})
            except self.acm_client.exceptions.ResourceInUseException:
                failed.append({certificate.arn: "Certificate in use."})
            except self.acm_client.exceptions.InvalidArnException:
                failed.append({certificate.arn: "Certificate has an invalid arn."})
            except Exception as e:
                if certificate:
                    failed.append({certificate.arn: "Uknown exception: {}".format(str(e))})
                else:
                    failed.append({"None": "Empty certificate specified."})
        return success, failed

    def request_certificate(self, identifier: str, domain_names: List[str]):
        """
        Request a certificate in ACM. The certificate's Tags.IDENTIFIER is set to the identifier argument
        and its Tags.STATE is set to States.PENDING. Mark all previously pending certificates with the same identifier for deletion.
        """
        pending_certificates = self.query(identifier=identifier, state=States.PENDING)
        certificate_tags = [
            {"Key": Tags.IDENTIFIER.value, "Value": identifier},
            {"Key": Tags.STATE.value, "Value": States.PENDING.value},
        ]
        request_certificate_args = {
            "DomainName": domain_names[0],
            "ValidationMethod": "DNS",
            "IdempotencyToken": "".join([random.choice(string.ascii_letters) for _ in range(32)]),
        }
        if len(domain_names) > 1:
            request_certificate_args["SubjectAlternativeNames"] = domain_names[1::]

        print("Requesting new certificate: {}".format(str(request_certificate_args)))
        requested_certificate = self.acm_client.request_certificate(**request_certificate_args)
        self.acm_client.add_tags_to_certificate(
            CertificateArn=requested_certificate["CertificateArn"], Tags=certificate_tags
        )
        self.mark_for_deletion(pending_certificates)

    def transition_to_available(self, certificates: List[Certificate]) -> None:
        """
        Transition the certificates passed as argument to the States.AVAILABLE state
        so long as its previous state was States.PENDING. Mark previously available certificates
        with the same identifier for deletion.
        """
        for certificate in certificates:
            if certificate.state == States.PENDING:
                previous_available = self.query(identifier=certificate.identifier, state=States.AVAILABLE)
                self.acm_client.add_tags_to_certificate(
                    CertificateArn=certificate.arn,
                    Tags=({"Key": Tags.STATE.value, "Value": States.AVAILABLE.value},),
                )
                self.mark_for_deletion(previous_available)
                self.ssm_client.put_parameter(
                    Name="/certifier/{}".format(certificate.identifier), Value=certificate.arn, Type="String"
                )

    def retry_failed(self, certificate: Certificate):
        """
        Determine which domains are part of the certificate and request it again.
        Mark failed certificate for deletion.
        """
        domains = self._get_domains_for_certificate(certificate)
        # request_certificate will also mark the failed certificate for deletion
        self.request_certificate(certificate.identifier, domains)

    def _get_domains_for_certificate(self, certificate) -> List[str]:
        """
        Describe the certificate in ACM to obtain the list of SubjectAlternativeNames and the DomainName it was requested with
        """
        certificate_data = self.acm_client.describe_certificate(CertificateArn=certificate.arn)["Certificate"]
        return [certificate_data["DomainName"]] + certificate_data["SubjectAlternativeNames"]

    def sns_notify(self, sns_topic_url: str, subject: str, message: str):
        pass


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
    * Make sure the S3 key only contains letters, numbers and the characters .-_ to make sure it's compatible with Parameter Store.

    Example of a create list:
    [("my_bucket", "key/to.my/object.first.txt", "key/to/object")]
    Example of a failure list:
    [("my_bucket", "key/to.my/object.first.txt", "the S3 object key contains invalid characters")]
    """
    if "Records" not in event:
        raise KeyError("'Records' key not found in event object")

    pattern = re.compile("([A-Za-z0-9]|-|_|\.|/)+")
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
            failed_reason += "Ignoring S3 folder object: 's3://{}/{}'. ".format(*certificate_file_data)

        if not pattern.fullmatch(certificate_file_data[1]):
            failed_reason += "The S3 object key '{}' does not match the pattern '{}'. ".format(
                certificate_file_data[1], pattern.pattern
            )

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
