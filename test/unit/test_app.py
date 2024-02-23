import pytest

from assessment.app import Assessment

host = "www.ssllabs.com"

@pytest.fixture
def assessment_default():
    return Assessment(host)

def test_constructor(assessment_default):
    assert isinstance(assessment_default, Assessment)
