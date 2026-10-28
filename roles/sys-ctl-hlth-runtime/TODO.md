# To-dos

- Extend `HEALTH_RUNTIME_FLOORS`, the container probe and `make security-runtimes` to `node`, `python`, `ruby` and `java`.
- Verify the web SAPI where an image splits it from the CLI. `web-app-lam` mounts the hardening ini into `/etc/php/8.4/apache2/conf.d`, which the Debian CLI does not scan, so `php` in that container reads the CLI configuration instead of the one Apache loads.
- Run `make security-runtimes` in a scheduled CI workflow.
- Scan the pinned images for CVEs (Trivy or Grype) in the scheduled CI and report new criticals as issues.
