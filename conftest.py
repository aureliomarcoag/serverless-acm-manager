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


import pathlib
import pytest  # type: ignore
from moto import mock_s3  # type: ignore
import boto3  # type: ignore


@pytest.fixture(scope="function")
def s3_client():
    mock = mock_s3()
    mock.start()
    s3_client = boto3.client("s3")
    yield s3_client
    mock.stop()


def pytest_runtest_setup(item):
    """
    Make the variable "test_files" available for the current test item.
    Open the directory "files/" located at the same level as the test file from
    which this test item originates and create a dict in which the key is the file name
    and the value is the respective Path object.
    """
    test_files_root = item.module.__file__
    if "test_files_root" in dir(pytest) and pytest.test_files_root == test_files_root:
        return

    test_files = {}
    for test_file in pathlib.Path(test_files_root).parent.joinpath("files").glob("*"):
        test_files[test_file.name] = test_file.absolute()
    pytest.test_files = test_files
    pytest.test_files_root = test_files_root
