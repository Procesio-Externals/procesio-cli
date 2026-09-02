# Contributing to procesio-cli

Thanks for helping improve the toolkit. You don't need any permission on this
repository to suggest a change. Everything below works from a normal GitHub
account.

## Ways to suggest an update

Pick the lightest one that fits.

| You want to | Do this |
| --- | --- |
| Fix a typo or a wrong sentence in a file | Open the file on GitHub and click the pencil icon. GitHub forks the repository for you and opens a pull request. |
| Report something that doesn't work | Open a [bug report](../../issues/new/choose). |
| Ask for a tool, an action, or a behavior | Open a [feature request](../../issues/new/choose). |
| Ask a question, or float an idea that isn't a request yet | Start a [discussion](../../discussions). |
| Change code | Fork the repository, push a branch, and open a pull request. |
| Report a security problem | Don't open an issue. See [SECURITY.md](SECURITY.md). |

For a change larger than a few lines, open an issue first. A maintainer tells
you whether the idea fits before you write the code.

## Open a pull request

1. Fork the repository and clone your fork.
2. Create a branch: `git checkout -b fix-form-dto-parsing`.
3. Install the dependencies: `uv sync`.
4. Make your change, and add a test that fails without it.
5. Run the suite: `uv run pytest`.
6. Push the branch and open a pull request against `main`.

The two commands CI will run on your branch:

```bash
uv run pytest tools agents dashboard webplatform -q
uv run python scripts/secret_scan.py
```

Leave **Allow edits by maintainers** checked. A maintainer can then push a small
correction to your branch instead of asking you for another round.

Every pull request lands as a single squashed commit, so you don't need to tidy
your history.

## What a maintainer looks for

- **One concern per pull request.** A refactor mixed into a bug fix takes far
  longer to review.
- **A test.** For a platform behavior, a test that captures the behavior is worth
  more than the fix itself.
- **Existing paths.** See the next section.
- **No new dependencies** without a reason in the pull request description. A
  package imported at module level has to be a base dependency; one imported
  inside a function may be an extra. CI checks that, and so does the export.
- **The manifest changes with the code.** `tool.yaml` declares a tool's actions,
  arguments and secrets, and it is what an assistant reads before running
  anything. A new argument that exists only in the handler is a bug, and the
  tests say so. After a manifest change, regenerate what is generated:
  `python scripts/build-tool-skill.py <tool>` and `python scripts/build-router.py`.
- **One JSON object on stdout, and nothing else.** Progress goes to stderr;
  failures print `{"error": {"code", "message", "details"}}` and exit non-zero.
  Callers parse that.

## Rules that come from how this repository is built

This repository is generated from an internal monorepo, not developed here
directly. An export tool copies files byte for byte, at identical paths. A
maintainer ports your merged pull request upstream by mapping its path, and it
comes back here verbatim on the next publish.

That gives you three rules:

- **Don't move or rename files.** A patch applies in both directions by path
  alone. A move breaks that, and the change has to be ported by hand.
- **Don't restructure a file to reformat it.** Same reason.
- **Expect small gaps.** A few upstream files carry marked regions that the
  export drops, so a sentence here can refer to something that is not in this
  tree. If a document points at something you can't find, that's why. Say so in
  an issue and a maintainer fixes the reference.

## Never commit these

The export refuses to publish a tree that contains any of them, and so does CI.

- `.procesio` platform export files. A platform export serializes Call API
  credentials inline. Treat every `.procesio` file as a secret, even one from a
  demo environment.
- Credentials, tokens, connection strings, and API keys, including in tests and
  fixtures. Read credentials through the credential store instead.
- Real workspace GUIDs, environment names, tenant names, or profile names.
- Personal names and email addresses, including in code comments.
- Anything identifying a customer: process names, notification bodies, sample
  payloads taken from a live system.

For an example, invent one. `contoso-demo`, `00000000-0000-0000-0000-000000000000`,
and `user@example.com` are all fine.

## Licensing

By opening a pull request, you agree that your contribution is licensed under
the same license as this repository, Apache 2.0, under the terms in section 5 of
the license. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
