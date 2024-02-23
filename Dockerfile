FROM python:3.10.13-slim-bullseye AS builder

RUN apt-get update && \
    apt-get upgrade --yes

RUN useradd --create-home assessment
USER assessment
WORKDIR /home/assessment

ENV VIRTUALENV=/home/assessment/venv
RUN python3 -m venv $VIRTUALENV
ENV PATH="$VIRTUALENV/bin:$PATH"

COPY --chown=assessment pyproject.toml constraints.txt ./
RUN python -m pip install --upgrade pip setuptools
RUN python -m pip install --no-cache-dir -c constraints.txt ".[dev]"

COPY --chown=assessment src/ src/
COPY --chown=assessment templates/ templates/
COPY --chown=assessment test/ test/

RUN python -m pip install . -c constraints.txt
RUN python -m pytest test/unit/
RUN python -m pytest -v test/e2e/
RUN python -m flake8 --ignore=E501 src/
RUN python -m isort src/ --check
RUN python -m black src/ --check --quiet
RUN python -m pylint src/ --fail-under=9 --disable=C0114,C0115,C0116,R1705
RUN python -m bandit -r src/ --quiet
RUN python -m pip wheel --wheel-dir dist/ . -c constraints.txt



FROM python:3.10.13-slim-bullseye

RUN apt-get update && \
    apt-get upgrade --yes

RUN useradd --create-home assessment
USER assessment
WORKDIR /home/assessment

ENV VIRTUALENV=/home/assessment/venv
RUN python3 -m venv $VIRTUALENV
ENV PATH="$VIRTUALENV/bin:$PATH"

COPY --from=builder /home/assessment/dist/assessment*.whl /home/assessment

RUN python -m pip install --upgrade pip setuptools
RUN python -m pip install --no-cache-dir assessment*.whl

COPY --chown=assessment templates/ templates/

CMD ["app"]
