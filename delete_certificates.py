import certifier

actions = certifier.actions()


def handler(event, context):
    actions.delete(actions.query(state=certifier.States.MARKED_FOR_DELETION))
