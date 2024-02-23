# Assessment


# 1. Overview

This "assessment" application grades an HTTPS endpoint according to the
security standards devised by SSL Labs.  It takes as an input one web domain,
in addition to various flags, and returns a security grade for each of the
associated endpoints.  Options include to allow cached reports or not, and to 
suppress or display all of the details of the security report returned by the
API of SSL Labs.

Details on the actual API [can be found here](https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md#protocol-usage).

# 2. Usage

## A. For use / production

Build the image, and then invoke locally.

- clone this repo
- ensure you have local Docker support
- build the container image:
  - `docker build -t assessment .`
- run the built image for the default website target ("www.ssllabs.com"), as a test:
  - `docker run assessment`
- and now run it for real, for a website you want:
  - `docker run -e HOST="www.google.com" assessment`

Sample output:

```
$ docker run -e HOST="www.google.com" assessment
~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
The following is a security report from SSL Labs for the 2 endpoint(s) associated with https://www.google.com.


Grades for endpoints that returned results:
lax02s27-in-x04.1e100.net (2607:f8b0:4007:801:0:0:0:2004): B
lax02s27-in-f4.1e100.net (172.217.12.132): B

~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
```

By default:
- a real-time progress report is provided, as results can take time to generate
- if a cached website report on the remote end exists, it is used
- only a summary grade for each associated endpoint is provided, not a detailed report

See the next section for how to alter this default behavior.

**Note again** that generating a report in non-cached mode will sometimes timeout.  This
somewhat dependent on what is going on with the servers at SSL Labs.

## B. Usage flags

Change the default behavior of the assessment application by supplying different flags:

| Flag            | Meaning                        | Supported Values       | Default Value | Required                               |
| --------------- | ------------------------------ | ---------------------- | ------------- | -------------------------------------- |
| HOST            | website domain name to analyze | <e.g. www.ssllabs.com> | <n/a>         | yes (unless you want the default site) |
| PROGRESS_REPORT | display progress bar           | True|False             | True          | no                                     |
| CACHED          | allow for cached results       | True|False             | True          | no                                     |
| RAW_RESULTS     | display full report            | True|False             | False         | no                                     |

For example, to see a non-cached report with full report details:

  - `docker run -e HOST="www.google.com" -e CACHED="False" -e RAW_RESULTS="True" assessment`

Sample output:

```
$ docker run -e HOST="www.google.com" -e CACHED="False" -e RAW_RESULTS="True" assessment
Gathering results with a backoff for https://www.google.com................................................................................................................................................................................................................................................Done
~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
The following is a security report from SSL Labs for the 2 endpoint(s) associated with https://www.google.com.


Grades for endpoints that returned results:
lax02s27-in-x04.1e100.net (2607:f8b0:4007:801:0:0:0:2004): B
lax02s27-in-f4.1e100.net (172.217.12.132): B

Raw results of the security query:
{
  &#34;host&#34;: &#34;https://www.google.com&#34;,
  &#34;port&#34;: 443,
  &#34;protocol&#34;: &#34;http&#34;,
  &#34;isPublic&#34;: false,
...
        &#34;drownHosts&#34;: [],
        &#34;drownErrors&#34;: true,
        &#34;drownVulnerable&#34;: false
      }
    }
  ]
}
~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
```

# 3. Roadmap / Plans for Future Development

## A. Some minor things missing that need to be / could be added

- docstrings (pylint errors for these are currently suppressed)
- type hints
- CLI help function
- converting some of the instance variables from public to private
- additional unit/end-to-end tests
- functions could be decomposed a bit
- perhaps divide Assessment class into two classes: a SslLabsApi class and an AssessmentRequest class

## B. More extensive resign for productionization and scaling out

**B1. "How would you scale this script and run it with resiliency to e.g. handle 1000s of domains?"**

- The key feature of the backend SSL Labs API is that its responses are not quick to support a synchronous REST architecture; an asynchronous one is needed
- Therefore, assuming a rate of queries as high as quoted in the question, a straightforward approach could be a poll-based serverless architecture as follows:
  - client makes an individual GET REST request for each domain
  - an AWS API Gateway receives the request and, for each such request, kicks off an AWS Lambda
    - the code in this report would need to be supplemented by a few additional Python files to wrap-around a REST layer
  - the Lambda places a request on an SQS queue, and then returns a 202 HTTP response and an S3 presigned-URL that will hold the report
  - an event-driven Lambda consumes from the SQS queue and polls for the result; on receipt, it populates the S3 bucket with an object linked to the pre-signed URL given to the user
  - all of the above to be built with Terraform/IaC
- This approach would have no scaling difficulties internally, but has at least two drawbacks:
  - [1] The client can't poll for status, but must instead continually check the presigned-URL; this could be mitigated by:
    - adding in a status endpoint that the client could poll, which would show when the report is available
    - sending an alert message to the client when the report is available
    - switching outright to a push model where the client provides a webhook and the system pushes a response to that endpoint on request completion
      - this does create more work for the client however
  - [2] it relies on the SSL Labs API being available and not being overwhelmed; this could be mitigated by internalizing its API, via [the Golang code available in their GitHub repo](https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-scan.go)
- If "resiliency" also means "disaster recovery", the service could be configured to run in a second AWS region with Route53 global load balancing

**B2. "How would you monitor/alert on this service?"**

- Assuming the above AWS architecture, error-handling would be implemented in the new Lambda wrap-around Python files
- Errors detected could be written to stderr in such a way that they would be picked up in AWS Cloudwatch logs
- AWS Cloudwatch alarms could then be configured to trigger SNS or email alerts; more ambitiously, a custom integration could be written to trigger a webhook, or even a Kafka message, to an arbitrary monitoring system
- This application is simple enough that there is probably not much to be gained by instrumenting it for APM

**B3. "What would you do to handle adding new domains to scan or certificate expiry events from your service?"**

- Regarding new domains
  - the above architecture could handle them fine -- the client would simply have to make additional requests
  - putting ourselves in the client's shoes, how could they handle it?  perhaps this:
    - a table in AWS DynamoDB consisting of a key with the website name and a subdictionary for each endpoint, initially holding just a security grade and timestamp
    - a step function that could be kicked off on a schedule that kicks off a query-and-wait-for-report-availability loop for each item in the DynamoDB table, updating the values there when the new grade becomes available
- To check for certificate expiry events:
  - [Certificate details associated with each endpoint](https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md#cert) include "notAfter" and "revocationStatus" that could be used to detect events
  - configuring support for this would require:
    - (trivial) a few new environment variable flags
    - (more substantive) breaking up the "gather_results" call in the code (currently) to separate the gathering of the results from deciding what to do with them -- just return them (as today), or take action based on specific field values (e.g. for certificate expiration)

**B4. "After some time, your report requires more enhancements requested by the Tech team of the company. How would you handle these "continuous" requirement changes in a sustainable manner?"**

- right now there is no CI/CD pipeline for this project
- creating one would not be too difficult though:
  - use GitHub Actions to:
    - build the Docker image with a tag matching the current Git commit
    - (the Dockerfile for this project already has unit and end-to-end tests built in, so need for a separate test stage)
    - assuming the build was successful, deploy it into the AWS architecture mentioned above via a Terraform run in the action itself, or via a preexisting pipeline
      - if in the action itself, store the state file in an S3 backend
- the service could be kept stable by supporting a development and production environment
  - the development environment would be an AWS account with all resources tied to an ephemeral branch, deleted on branch merge to main
  - the production environment would be a different AWS account, rebuilt on merge to main
    - it should be possible to use AWS CodeDeploy, or something similar, to update production without client-visible downtime
    - we would need to nail down SLOs for the service
- since we would be offering an API, it would need to be versioned and stable
  - we would use semantic versioning to differentiate between breaking and non-breaking changes
    - within a major version we would only add fields, e.g., not remove them
  - once an API version was published we would have to support it for an agreed-upon or indefinite period
- all of the above would make it easy to roll out changes in a quick and stable way; whether or not changes *should* be made would need to be worked out with management and in discussion with developer teams
  
# 4. Project Maintenance

## A. To build for local development

Build as above, or build the development image to keep support for testing:

  - `docker build -f Dockerfile.dev -t assessment .`

That will produce an image with test suite tools still installed.

## B. Dependency Updates

To update Python dependencies, regenerate the constraints file and then rebuild the container image.

`python -m pip freeze --exclude-editable > constraints.txt`

Don't forget to commit the updated contraints file back to source code.
