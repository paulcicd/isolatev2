FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server openssl sudo \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd \
    && useradd --create-home --user-group --shell /bin/sh enroll-service \
    && useradd --create-home --user-group --shell /bin/sh enroll-target \
    && printf 'root:%s\nenroll-target:%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" | chpasswd

WORKDIR /opt/isolate-fixture
COPY requirements-linux-py312.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-linux-py312.lock \
    && awk '/^[a-z0-9]/{print $1}' requirements-linux-py312.lock > /tmp/isolate-runtime-constraints.txt \
    && python -m pip install --no-cache-dir -c /tmp/isolate-runtime-constraints.txt 'ansible-core>=2.16,<2.20' 'fakeredis>=2.26,<3' \
    && ansible-galaxy collection install 'ansible.posix:==2.1.0'

COPY ansible/enroll-isolate-hosts.yml ansible/enroll-isolate-hosts.yml
COPY ansible/roles/isolate_host_enrollment/ ansible/roles/isolate_host_enrollment/
COPY shared/ shared/
COPY tests/test_admin_api.py tests/test_admin_api.py
COPY tests/integration/ansible/ tests/integration/ansible/

CMD ["python", "tests/integration/ansible/enrollment_apply.py"]
