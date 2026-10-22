# Windows Application Control diagnosis

**Scope:** read-only diagnosis of the Phase G.6 test-candidate artifacts at
commit `9fec0e2`. No Windows policy, registry value, exclusion, Scheduled
Task, certificate, installer, or application data was changed. The frozen EXE
was not re-run for this diagnosis.

## Conclusion

**Root cause (high confidence):** Windows Code Integrity blocked the unsigned
main frozen EXE under the active policy named
`VerifiedAndReputableDesktop`. The active policy GUID and name are strong
evidence for the Smart App Control “verified and reputable” policy path. It is
not an Excel, payroll, installer-staging, or bundled-DLL failure.

The precise source that enabled the policy (for example, a local Smart App
Control setting versus an enterprise-managed security configuration) cannot be
proved from the retained event data alone. This report does **not** claim to
have established the device-management origin. There is also no direct evidence
that the separate SmartScreen experience generated the block.

## Confirmed evidence

### Artifact integrity

The existing artifacts match the hashes recorded in
`06-installer-completion-report.md`.

| Artifact | Size | SHA-256 | Result |
| --- | ---: | --- | --- |
| `NTP Payroll Assistant - Test Candidate.exe` | 51,466,805 bytes | `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B` | Match |
| `NTP-Payroll-Assistant-Test-Candidate-Setup.exe` | 87,796,196 bytes | `D7C8C8E87B0D8FCBFE59737026A3AFA4B16D31AD3C6E56787500DF2C1C74A8DB` | Match |

Read-only `Get-AuthenticodeSignature` inspection reports both artifacts as
`NotSigned`, `SignatureType=None`, with no signer certificate or
thumbprint. The PowerShell status text also mentions execution policy; that
text is a generic message for an unsigned file and is not evidence that
PowerShell execution policy caused this application block.

### Code Integrity evidence

The `Microsoft-Windows-CodeIntegrity/Operational` log is enabled. User-mode
Code Integrity reports enforcement status `2` (enforced), and the active Code
Integrity policy directory contains
`{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}.cip`.

Six Event ID `3077` records, from `2026-10-22 15:47:21 +07:00` through
`15:47:57 +07:00`, identify the same main EXE. Personal path components are
redacted below.

| Event field | Observed value |
| --- | --- |
| Blocked filename | `NTP Payroll Assistant - Test Candidate.exe` |
| Redacted location | `<user-downloads>\NTP payroll\dist\build-…\NTP Payroll Assistant - Test Candidate\NTP Payroll Assistant - Test Candidate.exe` |
| SHA-256 Flat Hash | `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B` |
| Policy name | `VerifiedAndReputableDesktop` |
| Policy identity | `27555.1000.240208` |
| Active policy GUID | `{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}` |
| Status code | `0xc0e90002` |
| Requested / validated signing level | `2` / `1` |

This exact flat hash equals the current EXE SHA-256. The event names the EXE,
not an `_internal` DLL or Python extension. No Event ID `3077` record for a
bundled DLL was found when searching the retained operational log for this
artifact hash. Thus the confirmed initial block is the main EXE; the runtime
never reached a point where loading a bundled dependency could be assessed.

### Event ID 3089 correlation boundary

Event ID `3089` entries exist at the same timestamps, but their retained data
contains no filename. The nearest entries report `TotalSignatureCount=0`,
`SignatureType=0`, `PublisherName=Unknown`, `IssuerName=Unknown`,
`ValidatedSigningLevel=0`, `KnownRoot=0`, and
`VerificationError=0`. Their 20-byte hash is
`8047948CE3742E975FC1BFB1C4EF1FE596996B3B`, which is **not** the EXE’s SHA-1
(`847EA18B1E9EBF161C3D976BC8353DCA676F8BD4`). No retained Event ID `3089`
record bearing the EXE SHA-1 was found.

Accordingly, Event ID `3089` provides contextual evidence that unsigned code
was assessed around the block, but it cannot safely be attributed to this EXE.
The direct Authenticode result and Event ID `3077` are the definitive
evidence for this finding.

## Suspected policy classification

| Candidate source | Assessment | Reason |
| --- | --- | --- |
| Smart App Control / its verified-and-reputable policy | **High confidence** | The active policy GUID is the GUID reported by Windows for `VerifiedAndReputableDesktop`; the policy name in every block event is the same. Smart App Control is enforced through Code Integrity. |
| App Control for Business, organization-specific policy | Not established | The event identifies the verified-and-reputable policy, not an organization policy identity. Administrative policy provenance was not available through the safe, read-only checks. |
| SmartScreen prompt/reputation decision | Not established | The observed event is a Code Integrity enforcement event; no relevant SmartScreen event was available to correlate. |
| Bundled DLL / `.pyd` | Ruled out as the observed initial block | Event 3077 names the main EXE and the process did not launch. |

Microsoft describes Smart App Control as combining app intelligence with Code
Integrity and requiring unknown apps to be trusted or signed. It separately
documents that developers should sign executable files and all binaries they
ship. See [Smart App Control overview](https://learn.microsoft.com/windows/apps/develop/smart-app-control/overview),
[code-signing requirements](https://learn.microsoft.com/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control),
and [Windows application control guidance](https://learn.microsoft.com/windows/security/book/application-security-application-and-driver-control).

## Required legitimate resolution

1. A release owner must choose and obtain an approved identity: Microsoft
   Trusted Signing is the Microsoft-preferred route for this scenario, or an
   organization-validated code-signing certificate from a CA in the Microsoft
   Trusted Root Program. Do not create or trust a self-signed certificate.
2. In a secured release environment, Authenticode-sign and RFC 3161 timestamp
   every shipped PE binary: the frozen EXE, every shipped DLL / `.pyd` where
   applicable, and the setup and uninstaller generated by Inno Setup.
3. Rebuild staging only from the signed distribution, compile the installer
   with Inno Setup signing hooks for the setup/uninstaller, then record the new
   signed hashes and verify each signature. Signing necessarily changes file
   hashes, so the current hashes must not be reused.
4. If the device is enterprise managed, its authorized Windows security
   administrator must additionally confirm that the chosen publisher or
   Trusted Signing identity satisfies the organization’s App Control policy.
   Signing alone must not be represented as a guaranteed allow decision.
5. After an approved signed candidate is available, perform the already
   deferred disposable-environment install and frozen-runtime tests. Do not use
   a policy exception, exclusion, or bypass to make the unsigned candidate run.

For organization-managed deployments, Microsoft’s
[App Control code-signing guidance](https://learn.microsoft.com/windows/security/application-security/application-control/app-control-for-business/deployment/use-code-signing-for-better-control-and-protection)
should be used by the security owner to select the appropriate publisher,
catalog, or managed deployment rule.

## Packaging/signing configuration assessment

The current packaging scripts intentionally build an unsigned test candidate:

- `packaging/build_exe.ps1` invokes PyInstaller and verifies only a SHA-256.
- `packaging/build_installer.ps1` invokes Inno Setup after allowlisted staging.
- `packaging/installer/ntp_payroll.iss` has no Inno Setup `SignTool` directive.
- Repository search found no `signtool`, Authenticode, or trusted-signing
  configuration.

This is expected for the current candidate, but it is insufficient for a
trusted deployment. A future, separately authorized release-engineering change
is required to add secret-free signing integration (for example, parameters
that point to a secured signing service or agent), timestamp verification, and
post-signature manifest/hash generation. Signing secrets, certificate material,
tenant credentials, and certificate thumbprints must not be committed to this
repository.

## Authority boundary

### Actions Codex can perform after authorization

- Implement and test a secret-free build interface for an approved signing
  service or release agent.
- Add signature verification to packaging checks and regenerate release
  evidence after an authorized signed build.
- Test the signed candidate in the approved disposable environment.

### Actions requiring release owner or administrator authorization

- Purchase or enroll for a trusted signing identity and grant use of it.
- Configure a secured signing service, HSM, or protected release agent.
- Approve publisher trust or App Control policy changes for managed devices.
- Authorize installation and uninstall testing in a disposable Windows
  environment.

No such authority was assumed or exercised during this diagnosis.

## Remaining Final Acceptance blockers

1. An approved signing and trusted-deployment decision is required.
2. A signed candidate must pass Authenticode verification and applicable
   Windows policy assessment without exceptions.
3. Frozen native UI, tray, keyboard/DPI, packaged Excel COM, installer
   install/upgrade/uninstall, and clean-machine tests remain deferred until a
   legitimately trusted candidate can run in an authorized disposable
   environment.
4. Production activation remains disabled and is outside this diagnosis.

## Recommended next safe action

Have the release owner and Windows security administrator confirm whether this
device is governed by Smart App Control alone or an organization App Control
policy, then approve a Microsoft Trusted Signing or trusted-CA signing route.
Only after that decision should a separate, reviewable signing-integration
session begin. Do not alter local Windows protections to test the unsigned
candidate.
