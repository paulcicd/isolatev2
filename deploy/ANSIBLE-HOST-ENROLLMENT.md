# Enroll SSH hosts with Ansible

Add [the enrollment role](../ansible/roles/isolate_host_enrollment) after provisioning the target Unix account. The provided playbook runs against one target at a time and prints its numeric Isolate host ID for subsequent operations.

## Configure the inventory

Copy [the sample inventory](../ansible/enroll-hosts.example.yml). Add managed hosts to `isolate_enrollment_targets` and supply these values for the deployment.

| Variable | Value |
| --- | --- |
| `isolate_enrollment_api_origin` | HTTPS origin of the Isolate control API. Set `isolate_enrollment_tls_ca_file` to your CA bundle on the controller if it uses a private CA. |
| `isolate_enrollment_bastion` | Inventory alias of the bastion host. Its provisioning login must be able to become root and the Isolate service account. |
| `isolate_enrollment_external_id` | Stable machine identifier from your CMDB or provisioning system. Use one value per managed host across projects. |
| `isolate_enrollment_server_id` | Optional numeric Isolate ID from a previous enrollment. Record it for automation that will move to another workload identity. Enrollment then requires that exact record to be visible under the external ID. |
| `isolate_enrollment_project` | Existing administrative project scope for the host. Policies for this project apply when the host is registered. |
| `isolate_enrollment_ssh_user` | Existing Unix account that accepts Isolate connections to the target. |
| `isolate_enrollment_ssh_address`, `isolate_enrollment_ssh_port` | Address and port from the bastion. Defaults come from `ansible_host` and `ansible_port`. Use a numeric address for the inventory record. |
| `isolate_enrollment_bastion_identity_file` | Path of the service account SSH identity on the bastion, with its matching `.pub` file. Defaults to `/home/auth/.ssh/id_ed25519`. |
| `isolate_enrollment_known_hosts_files` | Absolute trust-store paths on the bastion. List each path read by the gateway and the runbook worker. Create the parent directories as part of bastion provisioning. |
| `isolate_enrollment_target_host_key_file` | Ed25519 host public-key file on the target. Defaults to `/etc/ssh/ssh_host_ed25519_key.pub`. |
| `isolate_enrollment_tags` | Optional inventory tags as a mapping. The role preserves existing tags and records the external ID as `isolate_enrollment_id`. |

The playbook uses the controller's existing SSH trust for both the target and the bastion. Provision those pins through your existing management channel first. The target provisioning login must be able to read its host public key and manage `authorized_keys` for the selected Unix account. This role is intended for targets reachable directly from the bastion with its configured file-backed service identity.

## Run enrollment

Use a Linux Ansible controller with `ansible-core` 2.14 or later and `ansible.posix`. Configure a dedicated OIDC workload client with `inventory.write` for the required `admin_projects`. Export its short-lived access token with scope `isolate.inventory.write` as `ISOLATE_TOKEN` using your CI credential store. See the [workload configuration in the Terraform provider docs](../terraform-provider-isolate/README.md#authentication-and-authorization).

```sh
ansible-galaxy collection install ansible.posix
ansible-playbook -i hosts.yml ansible/enroll-isolate-hosts.yml --check
ansible-playbook -i hosts.yml ansible/enroll-isolate-hosts.yml
```

Check mode reads the scoped catalog and reports the planned inventory operation. During enrollment, the role reads the host public key through the pinned provisioning connection, installs the bastion service public key on the selected target account, and records the host key in the configured trust stores. It tests noninteractive SSH from the bastion before registering the host, reads back the saved record, and repeats the SSH check for that record.

Use a single job at a time per bastion when changing shared `known_hosts` files. Re-running enrollment with the same external ID reuses the matching record. The API uses a stable create intent per workload identity for retries and the current revision for updates. For a workload or project migration, reconcile the numeric host ID and permissions first. If Isolate reports a conflicting record or a stale revision, check inventory before retrying. For an existing manually registered host, confirm its project, IP, port, and account, then set its `isolate_enrollment_id` tag to the external ID before running the role. Review any conflicting SSH host key in the bastion trust stores as a separate rotation.
