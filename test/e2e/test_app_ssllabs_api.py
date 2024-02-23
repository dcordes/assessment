import pytest
import requests

from assessment.app import Assessment

host = "www.ssllabs.com"

@pytest.mark.timeout(30)
def test_ssllabs_analyze():
    assessment = Assessment(host, progress_report=False, cached=True, raw_results=False)
    assessment.analyze()
    assert assessment.remote_request_status != "ERROR"

@pytest.mark.timeout(30)
def test_gather_results():
    assessment = Assessment(host, progress_report=False, cached=True, raw_results=False)
    results = assessment.gather_results()
    assert "The following is a security report from SSL Labs for the 1 endpoint(s) associated with https://www.ssllabs.com." in results
