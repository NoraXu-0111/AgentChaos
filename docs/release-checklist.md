# v0 publish checklist

This checklist is for publishing `agentchaos` v0.1.0 publicly.

## Manual gates

- The repository is public before launch posts go out.
- PyPI project ownership is confirmed for `agentchaos`.
- `pip install agentchaos` works in a clean virtual environment after publish.
- The refund-agent demo reproduces the baseline PASS and regression FAIL report.
- The README's example output still matches the demo closely enough to be honest.
- You have time to respond to launch feedback during the first hour.

## Local verification

From the repo root:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev mypy agentchaos
uv run --extra dev pytest -q --cov=agentchaos --cov-report=term
uv build
uv publish --dry-run
```

Expected current state:

- Test suite: 123 tests passing.
- Coverage: at least 85% total; current local run was 96%.
- Wheel and sdist exist under `dist/`.

## Demo verification

Start the demo:

```bash
cd examples/refund-agent
uvicorn server.main:app --host 127.0.0.1 --port 8080
```

In another shell:

```bash
agentchaos doctor scenarios/01-happy-path.yaml
agentchaos run scenarios/02-rag-cost-regression.yaml --out /tmp/agentchaos-demo-baseline.jsonl
```

Restart the demo with a higher RAG chunk count:

```bash
RAG_CHUNKS=12 uvicorn server.main:app --host 127.0.0.1 --port 8080
```

Then run:

```bash
agentchaos run scenarios/02-rag-cost-regression.yaml \
  --baseline /tmp/agentchaos-demo-baseline.jsonl \
  --out /tmp/agentchaos-demo-candidate.jsonl
```

Expected result:

- Baseline exits `0`.
- Candidate exits `2`.
- Report contains `max_cost_regression_pct`, `max_input_token_regression_pct`,
  and `metadata.rag_chunks changed`.

## Publish

Use one of these authentication paths:

- PyPI trusted publishing: configure the PyPI project for this GitHub repo, then
  publish from the approved environment with `uv publish --trusted-publishing`.
- PyPI API token: set `UV_PUBLISH_TOKEN` or pass `--token`.

Publish command:

```bash
uv publish
```

Immediately verify from a clean environment:

```bash
python -m venv /tmp/agentchaos-install-check
source /tmp/agentchaos-install-check/bin/activate
pip install agentchaos
agentchaos --version
agentchaos --help
deactivate
```

## GitHub release

After PyPI succeeds:

```bash
git tag -a v0.1.0 -m "v0.1.0 - first public release"
git push origin v0.1.0
gh release create v0.1.0 \
  --title "v0.1.0 - first public release" \
  --notes-file docs/launch/release-v0.1.0.md
```

## Launch

Before posting:

- Confirm the repo visibility is public.
- Confirm the install command in the README works.
- Confirm issue templates and the PR template are present.
- Read `docs/launch/posts.md` and tune the voice for the target channel.
- Do not announce v1 chaos as shipped. It is a roadmap item gated by traction or
  a design partner request.
