import json
import pytest
import handlers


def test_get_certificates_from_s3_event():
    with pytest.test_files["s3_event_created.json"].open() as event_created_file, pytest.test_files[
        "s3_event_removed.json"
    ].open() as event_removed_file, pytest.test_files["s3_event_invalid_item.json"].open() as event_invalid_item_file:
        event_created = json.loads(event_created_file.read())
        event_removed = json.loads(event_removed_file.read())
        event_invalid_item = json.loads(event_invalid_item_file.read())
    delete, create, failed = handlers.get_certificates_from_s3_event(event_created)
    assert len(create) == 1 and len(delete) == len(failed) == 0
    delete, create, failed = handlers.get_certificates_from_s3_event(event_removed)
    assert len(delete) == 1 and len(create) == len(failed) == 0
    delete, create, failed = handlers.get_certificates_from_s3_event(event_invalid_item)
    assert len(failed) == 1 and len(create) == len(delete) == 0


# def test_get_file_from_s3(s3_client):
