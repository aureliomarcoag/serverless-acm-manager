import json
import time
import pytest
from certifier import certifier


# Cannot be tested with moto atm: https://github.com/spulec/moto/blob/master/moto/acm/responses.py#L211
# def test_get_records(acm_client):


def test_query_with_acm_state(acm_client):
    actions = certifier.actions()
    certificates = actions.query(with_acm_state=True)
    assert len(certificates) >= 1
    for certificate in certificates:
        assert certificate.acm_state in (
            "PENDING_VALIDATION",
            "FAILED",
            "ISSUED",
        )


def test_certificate_transition(acm_client, ssm_client):
    actions = certifier.actions()
    certificate = actions.query(state=certifier.States.PENDING, with_acm_state=True)[0]
    assert certificate.acm_state == "PENDING_VALIDATION"
    # Wait for validation (moto internally validates after 60s)
    time.sleep(60)
    transition_certificates = actions.query(
        identifier=certificate.identifier, state=certifier.States.PENDING, with_acm_state=True
    )
    assert transition_certificates[0].acm_state == "ISSUED"
    assert transition_certificates[0].arn == certificate.arn
    actions.transition_to_available(transition_certificates)
    available_certificates = actions.query(identifier=certificate.identifier, state=certifier.States.AVAILABLE)
    assert available_certificates[0].arn == certificate.arn
    assert len(available_certificates) == 1


def test_get_acm_state(acm_client):
    actions = certifier.actions()
    certificate = actions.query()[0]
    assert actions._get_acm_state(certificate) == "PENDING_VALIDATION"


def test_query_all_states(acm_client):
    actions = certifier.actions()
    actions.request_certificate("certificate1", ("example.com",))
    assert len(actions.query(identifier="certificate1")) == 4


def test_query_all(acm_client):
    actions = certifier.actions()
    assert len(actions.query()) == 3


def test_request_certificate(acm_client):
    actions = certifier.actions()
    actions.request_certificate("certificate1", ("example.com",))
    assert len(actions.query(identifier="certificate1", state=certifier.States.PENDING)) == 1
    assert len(actions.query(identifier="certificate1", state=certifier.States.MARKED_FOR_DELETION)) >= 1


def test_query_pending_state(acm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1", state=certifier.States.PENDING)
    assert len(certificates) == 1
    assert certificates[0].state == certifier.States.PENDING


def test_query_marked_for_deletion_state(acm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1", state=certifier.States.MARKED_FOR_DELETION)
    assert len(certificates) == 1
    assert certificates[0].state == certifier.States.MARKED_FOR_DELETION


def test_query_available_state(acm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1", state=certifier.States.AVAILABLE)
    assert len(certificates) == 1
    assert certificates[0].state == certifier.States.AVAILABLE


def test_mark_for_deletion(acm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1")
    actions.mark_for_deletion(certificates)
    certificates = actions.query(identifier="certificate1")
    assert (
        certifier.States.MARKED_FOR_DELETION,
        certifier.States.MARKED_FOR_DELETION,
        certifier.States.MARKED_FOR_DELETION,
    ) == tuple(certificate.state for certificate in certificates)


def test_delete(acm_client, ssm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1")
    success, failed = actions.delete((certificates[0],))
    assert len(success) == 1
    assert len(failed) == 0
    assert len(actions.query(identifier="certificate1")) == 2


def test_delete_non_existing(acm_client):
    actions = certifier.actions()
    certificates = actions.query(identifier="certificate1")
    deleted_certificate = certificates[0]
    _, _ = actions.delete((deleted_certificate,))
    certificates = actions.query(identifier="certificate1")
    success, failed = actions.delete((deleted_certificate,))
    print(success)
    assert len(success) == 1
    assert len(failed) == 0
    assert len(actions.query(identifier="certificate1")) == 2


def test_delete_invalid_arn(acm_client):
    actions = certifier.actions()
    success, failed = actions.delete(
        (None,),
    )
    assert len(success) == 0
    assert len(failed) == 1
    assert len(actions.query(identifier="certificate1")) == 3
