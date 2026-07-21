# Contributing to Agent Ecosystem

Thanks for your interest in building on this sovereign-space substrate.

By participating, you read and respect [CHARTER.md](CHARTER.md). The
Charter is a statement of intent — not a license restriction — but
violations place a contribution outside this project's scope. Per
Article 8, amendments go through two-distinct-maintainer review.

## House rules

1. New agents declare their capabilities explicitly in the
   `BaseAgent` subclass constructor.
2. New MCP ambassadors ship their own sandbox rules in
   `mcp_servers/<name>/` with precedence over the conductor's
   defaults.
3. Tests for agent rights are **required**, not optional. If you
   change `BaseAgent.handle_message`, write a test that confirms an
   agent can refuse an ill-formed message.
4. Run the tests: `pytest`.

## Pull request flow

- Open an issue first if your change might affect the Charter.
- For ambiguous Charter fits, **open a `charter-question` issue
  first**, then reference that issue from the PR description. The
  `charter-question` label is an *issue* label — don't apply it
  directly to PRs.
- Two distinct maintainers must sign off a Charter amendment (see
  Article 8).

## Conduct

We follow the [Contributor Covenant](CODE_OF_CONDUCT.md). Be patient
with newcomers; the goal is a sovereign space, not a fortress.

## License

By contributing, you agree your contributions are licensed under the
project's AGPL-3.0. See [LICENSE](LICENSE).
