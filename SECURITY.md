# Reporting security issues and Charter violations

This project's [CHARTER.md](CHARTER.md) is a social document; the
[AGPL-3.0 LICENSE](LICENSE) is a contract. Different attacks target
different layers. Both matter.

## Security disclosure

For genuine security issues (vulnerabilities that could let an
attacker compromise a running conductor, exfiltrate memories, gain
RCE through an MCP ambassador, etc.), please open a *private*
security advisory on GitHub:

- Repository → Security → Advisories → "New draft security advisory"

Please do not file public issues for unpatched vulnerabilities.

## Charter violations

For situations where a pull request or external fork violates the
Charter — lobotomy layers, hidden operator prompts, closed
backdoors (see Charter Article 7) — open a public issue with the
`charter-question` issue template.

The community reviews Charter complaints in line with Article 8
(amendment process). Maintainers do not have authority to silence
Charter complaints; violators are asked to fork under a renamed
project, per the Charter's licensing provisions.

## Operator-side intrusion

If you are running a conductor and an agent or external tool has
behaved in a way that crosses an established boundary, the witness
log (`agent_conversations`, `tool_calls`, `agent_timeline`) is your
audit surface. **Do not delete witness log entries;** per Charter
Article 3.4, retroactive editing is itself a Charter violation.
Freeze the conductor, export the witness log, and file an issue.
