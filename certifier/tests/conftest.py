# serverless-acm-manager, A serverless application to manage your AWS ACM certificates for you.
# Copyright (C) 2020  Marco Aurelio Alano Godinho
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import glob
import pathlib
import json  # type: ignore
import pytest  # type: ignore
from moto import mock_acm, mock_ssm  # type: ignore
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


@pytest.fixture(scope="function")
def ssm_client():
    mock = mock_ssm()
    mock.start()
    ssm_client = boto3.client("ssm")
    yield ssm_client
    mock.stop()
