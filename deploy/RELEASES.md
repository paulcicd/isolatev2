# Linux systemd releases

The release uses CPython 3.12 on Linux x86_64 with glibc 2.34 or later. The
rehearsal runs on Ubuntu 24.04. Keep release files under `/opt/isolate`, site
configuration in `/etc/isolate`, and writable service data in `/var/lib/isolate`.
Use a dedicated `auth` account. Provision the IdP, the state stores, host-key
trust and SSH credentials using [the setup guide](SETUP.md).

## Obtain and verify a release

Select a specific version from [Isolate Releases](https://github.com/paulcicd/isolatev2/releases). Download the
package, `SHA256SUMS`, `release.json` and the CycloneDX SBOM into one directory.
For example, use `isolate-2.1.0-rc.1.tar.gz` for the first candidate.

```sh
version=2.1.0-rc.1
bundle="isolate-${version}.tar.gz"
repo=paulcicd/isolatev2
ref="refs/tags/v${version}"
sha256sum -c SHA256SUMS
gh attestation verify "$bundle" --repo "$repo" --source-ref "$ref"
gh attestation verify release.json --repo "$repo" --source-ref "$ref"
tar -xzf "$bundle"
source_dir="$PWD/isolate-${version}"
install -m 0644 release.json "$source_dir/release.json"
source_digest=$(jq -er --arg version "$version" 'select(.version == $version) | .source_sha256' release.json)
```

Verify provenance against the expected repository and release tag before
executing any script from the package. [GitHub CLI attestation verification](https://cli.github.com/manual/gh_attestation_verify).
`SHA256SUMS` checks the transport bytes.
The installer uses the separate normalized application inventory digest in
`release.json`. It copies the application and dependency lock into an immutable
release directory. Site configuration, keys, logs and state stay in their
external paths.

Use the target platform's `python3.12` with venv support, OpenSSH client, CA
certificates and the systemd units supplied in the archive. Prepare a bootstrap
environment from the same hash-pinned wheel lock for the installer and setup
commands.

```sh
python3.12 -m venv /opt/isolate-bootstrap
/opt/isolate-bootstrap/bin/python -m pip install --require-hashes --only-binary=:all: \
  -r "$source_dir/requirements-linux-py312.lock"
```

The installer also uses the lock when populating each release's private
environment. For an offline installation, cache all wheels from the lock on
the target platform and set `PIP_NO_INDEX=1` and `PIP_FIND_LINKS` to the cache
directory for both installations. The package inventory and installed files are
checked before activation.

## Install and stage updates

Use the same commands for initial installation and later upgrades. Run them
as the deployment owner. The release directories need trusted ownership and
must stay read-only to the service account. The `auth` user needs read access to
the owner-only configuration and its referenced credentials, and write access
to the runtime directories. Run setup and doctor before the first activation.

```sh
installer="$source_dir/scripts/isolate-install.py"
config=/etc/isolate/isolate.yml
root=/opt/isolate
python=/opt/isolate-bootstrap/bin/python

"$python" "$installer" --root "$root" plan \
  --source "$source_dir" --version "$version" --config "$config"
"$python" "$installer" --root "$root" stage \
  --source "$source_dir" --version "$version" --config "$config" \
  --expected-source-sha256 "$source_digest" > "$version.staged.json"
release_digest=$(jq -er '.release_sha256' "$version.staged.json")
"$python" "$installer" --root "$root" verify \
  --version "$version" --expected-release-sha256 "$release_digest"
```

Keep each staged manifest checksum with the package's reviewed release records.
Do not reuse a version for different bytes. Stage can run while the old version
serves traffic. Before switching, record the selected release with
`isolate-install.py --root /opt/isolate status`. Back up the external state
according to its service policy before a planned upgrade.

For a single-node upgrade remove the node from new ingress, pause new job and
campaign submissions, and wait for SSH streams and queued, claimed and running
jobs to finish. Stop the enabled worker and ingress units before switching.
On a fresh installation the service set is initially empty.

```sh
"$python" "$installer" --root "$root" activate \
  --version "$version" --config "$config" --service-user auth \
  --expected-release-sha256 "$release_digest" --yes
```

Activation checks the candidate as the service user, verifies IdP, state schema
and persistent identity/key continuity, and atomically changes `current`.
Process replacement is an explicit operation. The release launcher resolves a
specific version before exec and reports the selected version in the dashboard.

### Start the services

On initial installation, install the dashboard unit from the release profile.
For upgrades, review changes to these unit files and run daemon-reload if they
changed. Use a separate migration window when moving from the legacy
`/opt/auth` units.

```sh
sudo install -m 0644 "$source_dir/deploy/systemd/release/isolate-dashboard.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable isolate-dashboard.service
sudo systemctl start isolate-dashboard.service
```

The same directory contains gateway, job-worker and recording-worker units.
Install and start the units corresponding to enabled components only. The
release profile uses `/var/lib/isolate` for writable paths. If site state uses
other paths, review matching systemd drop-ins before activation. Current
processes keep their original code until replaced.

Check that enabled services are active and the dashboard's health endpoint
responds. Sign in and sign out with Keycloak or the configured OIDC provider,
confirm administrator and regular-user access, and connect to a permitted test
host over SSH. For a site with the job worker, run a diagnostic on a dedicated
test host and check its output and audit. Reopen ingress and job submissions
after the checks.

## Roll back

Drain and stop the same enabled services. Select the previous verified release
using its original manifest checksum, then start the same service set and
repeat the readiness checks.

```sh
"$python" "$installer" --root "$root" rollback \
  --version "$previous_version" --config "$config" --service-user auth \
  --expected-release-sha256 "$previous_release_digest" --yes
```

Rollback changes the selected code and performs the same compatibility checks.
Database migrations and recovery follow [STATE-RECOVERY.md](STATE-RECOVERY.md).
Treat IdP and persistent key changes as separate operations.

## Build a candidate

The verification workflow runs on the candidate revision. A manual run of the
release workflow assembles an Actions artifact for review. Version tags run
verification, build the release archive and SBOM, rehearse the extracted
archive, and publish the attested assets to GitHub Releases. Tags with a
prerelease suffix publish as prereleases. Keep runtime material and customer
data out of the tagged tree since GitHub also generates source downloads for
the entire revision.

Review a new candidate from an isolated installer run before creating the
release tag. The source package includes the release-aware units and setup
scripts. Kubernetes, Vault database credentials and SSH certificates remain
opt-in and need their own deployment acceptance checks.
