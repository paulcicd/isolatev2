# Changelog

## 2.1.0-rc.1

- Adds the bilingual administration interface with an inventory, access matrix,
  audit search, profile settings and light, dark and system themes.
- Adds Web SSH workspaces with full-screen and separate-window modes, session
  replay, readable transcripts and terminal output history.
- Adds administrator-managed runbook drafts, versioned publishing and
  canary-first campaigns with per-host results.
- Preserves buffered Runbook output when a short SSH command exits.
- Adds Ansible enrollment for managed SSH targets through the scoped inventory
  API and verified host-key trust.
- Adds versioned Linux/systemd packages with locked runtime wheels, published
  checksums, a dependency SBOM, provenance, and staged upgrades and rollback.
- Keeps Kubernetes streams, mediated database access, web applications and
  Vault/OpenBao SSH certificates opt-in. Follow the individual protocol guides
  and verify the target infrastructure before enabling them.
