import json
import os
import time

import requests
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateSyntaxError


# this class is intended to support fresh test results only
# API details here: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
#
# basic workflow:
#   -- make an initial request with a "start" flag
#   -- make identical requests, without that flag, until status is READY|ERROR
#   -- process results
#
class Assessment:
    base_url = "https://api.ssllabs.com/api/v2/"

    # control flags:
    #   progress_report: set to True to see user-friendly stdout
    #   formatted: set to False to receive raw JSON output
    #   cached: set to True to force a non-cached result
    #   raw_results: include the complete JSON report in the final formatted
    #                report (ignored if formatted=False)
    def __init__(
        self,
        host,
        progress_report=False,
        formatted=True,
        cached=True,
        raw_results=False,
    ):
        self.host = f"https://{host}"
        self.remote_request_status = (None,)  # DNS, ERROR, IN_PROGRESS, READY
        self.complete = False
        self.state_description = "healthy"
        self.remote_results = {}
        # Control flags
        self.progress_report = progress_report
        self.formatted = formatted
        self.raw_results = raw_results
        self.initial_request = True
        if cached:
            self.initial_params = {
                "host": {self.host},
                "fromCache": "on",
                "maxAge": "24",
                "all": "done",
            }
            self.subsequent_params = self.initial_params
        else:
            self.initial_params = {"host": {self.host}, "startNew": "on", "all": "done"}
            self.subsequent_params = {"host": {self.host}, "all": "done"}

    def analyze(self):
        url = f"{Assessment.base_url}analyze"
        if self.initial_request:
            payload = self.initial_params
            self.initial_request = False
        else:
            payload = self.subsequent_params
        #
        try:
            # wait 2 seconds to connect; 5 for a response
            response = requests.get(url, params=payload, timeout=(2, 5))
        except requests.exceptions.ConnectTimeout as e:
            self.complete = True
            self.state_description = (
                f"The assessment service took too long to initiate a connection: {e}"
            )
            return
        except requests.exceptions.ReadTimeout as e:
            self.complete = True
            self.state_description = (
                f"The assessment service took too long to respond: {e}"
            )
            return
        except requests.exceptions.RequestException as e:
            self.complete = True
            self.state_description = (
                f"The assessment service responded with an HTTP error: {e}"
            )
            return
        except Exception as e:
            self.complete = True
            self.state_description = (
                f"An error has occurred querying the SSL assessment service: {e}."
            )
            return

        # https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md#error-response-status-codes
        if response.status_code != 200:
            if response.status_code == 404:
                error_text = "HTTP client error!"
            elif response.status_code == 400:
                error_text = "Invalid query parameters!"
            elif response.status_code == 429:
                error_text = "Too frequent polling!"
            elif response.status_code == 500:
                error_text = "Internal error on remote server side!"
            elif response.status_code == 503:
                error_text = "Remote system unavailable!"
            elif response.status_code == 529:
                error_text = "Remote system is overloaded!"
            elif "statusMessage" in response.json():
                error_text = response.json()["statusMessage"]
            else:
                error_text = response.json()["errors"]
            self.complete = True
            self.state_description = f"The service responded with an error!: {response.status_code}: {error_text}"
            return

        self.remote_request_status = response.json()["status"]
        if self.remote_request_status == "READY":
            self.remote_results = response.json()
            self.complete = True
        elif self.remote_request_status == "ERROR":
            self.state_description = response.json()["statusMessage"]
            self.complete = True

    def gather_results(self):
        seconds = 0
        second_ceiling = 30
        self.analyze()
        if not self.complete and self.progress_report:
            print(
                f"Gathering results with a backoff for {self.host}",
                end="",
                flush=True,
            )

            while not self.complete and seconds <= second_ceiling:
                seconds += 2
                if self.progress_report:
                    print("." * seconds, end="", flush=True)
                time.sleep(seconds)
                self.analyze()

            if self.progress_report:
                print("Done")

            self.complete = True

            if seconds > second_ceiling:
                self.state_description = f"The assessment service did not complete its analysis in the time allowed, waiting on the last try for {second_ceiling} seconds)."

        if self.state_description != "healthy":
            return f"Error retrieving results for {self.host}: {self.state_description}"
        elif self.formatted:
            return self.__formatted_results()
        else:
            return self.remote_results

    def __formatted_results(self):
        good_endpoints = []
        bad_endpoints = []
        for endpoint in self.remote_results["endpoints"]:
            if endpoint["statusMessage"] == "Ready":
                good_endpoints.append(endpoint)
            else:
                bad_endpoints.append(endpoint)
        #
        environment = Environment(
            loader=FileSystemLoader("templates/"), autoescape=True
        )
        try:
            template = environment.get_template("report.jinja")
        except TemplateSyntaxError as e:
            self.complete = True
            self.state_description = (
                f"The internal Jinja template failed to render: {e}"
            )
            return f"Error retrieving results for {self.host}: {self.state_description}"
        content = template.render(
            host=self.host,
            endpoint_count=len(self.remote_results["endpoints"]),
            bad_endpoints=bad_endpoints,
            good_endpoints=good_endpoints,
            raw_results=self.raw_results,
            results=json.dumps(self.remote_results, indent=2),
        )
        return content


def main():
    host = os.environ.get("HOST", "www.ssllabs.com")
    #
    # str --> boolean conversions
    progress_report_str = os.environ.get("PROGRESS_REPORT", "True")
    if progress_report_str == "True":
        progress_report = True
    else:
        progress_report = False
    #
    cached_str = os.environ.get("CACHED", "True")
    if cached_str == "True":
        cached = True
    else:
        cached = False
    #
    raw_results_str = os.environ.get("RAW_RESULTS", "False")
    if raw_results_str == "True":
        raw_results = True
    else:
        raw_results = False
    #
    assessment = Assessment(
        host=host,
        progress_report=progress_report,
        cached=cached,
        raw_results=raw_results,
    )
    results = assessment.gather_results()
    print(results)


if __name__ == "__main__":
    main()
