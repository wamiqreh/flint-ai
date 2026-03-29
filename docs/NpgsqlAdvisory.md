Npgsql Advisory

Summary:
- NuGet resolved Npgsql 8.0.0 in this environment and a public advisory (GHSA-x9vc-6hfv-hg8c) exists for that version.

Decision taken for repository:
- Keep csproj references at Npgsql 7.2.0 (legacy target) to avoid pulling 8.x where possible.
- For development and CI in this repo, accept the current resolved version but schedule remediation: file an issue to pin to a secure version or apply vendor patch.

Recommended next steps:
1. Audit dependent packages that force Npgsql 8.x and update package sources to ensure 7.2.0 is resolvable in CI.
2. If 7.2.0 is not available on feeds, plan migration to a patched 8.x release once vendor publishes advisory fix.
3. Add an automated dependency scan (e.g., GitHub Dependabot) to track advisories.
