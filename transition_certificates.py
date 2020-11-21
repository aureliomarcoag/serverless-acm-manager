import certifier

actions = certifier.actions()


def handler(event, context):
    certificates = actions.query(with_acm_state=True)
    for certificate in certificates:
        if certificate.state == certifier.States.PENDING:
            if certificate.acm_state == "FAILED":
                print("Failed to validate certificate, retrying: {}".format(str(certificate)))
                actions.retry_failed(certificate)
            if certificate.acm_state == "ISSUED":
                print("Transitioning certificate to available state: {}".format(str(certificate)))
                actions.transition_to_available([certificate])
