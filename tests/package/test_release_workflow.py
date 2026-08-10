"""Structural tests for the tag-triggered CI publish workflow and release-notes config.

``.github/workflows/release.yml`` is the CI half of the release pipeline:
``scripts/release.sh`` (the human half) pushes an annotated tag ``vX.Y.Z``; this
workflow triggers on ``v*``, builds the canonical ``jrag-cli`` dist and the
``java-codebase-rag`` shim, guards each, publishes both to PyPI via OIDC
Trusted Publishing (no stored token), verifies both names report the tag's
version, and opens a GitHub Release with auto-categorized notes.
``.github/release.yml`` is GitHub's release-notes categorization config that
the Release step's ``generate_release_notes: true`` consumes (note: same
basename, different directory — ``.github/`` root, NOT ``workflows/``).

These are *structural* tests: they assert on the keys that encode the
invariants (tag trigger, OIDC permission, ``release`` environment, dry-run
rehearsal input, notes categorization + chore exclusion), not on formatting.
``yaml.safe_load`` is available via ``pyyaml`` (already a runtime dep).

YAML gotcha: PyYAML (YAML 1.1) parses the bare workflow key ``on:`` as the
boolean ``True`` (because ``on``/``off``/``yes``/``no`` are bare booleans).
``_triggers()`` reads either spelling so the test survives either workflow
style (``on:`` as a map vs. an explicit ``"on":`` string key).
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
NOTES = REPO_ROOT / ".github" / "release.yml"


def _load(path: Path) -> dict:
    """``yaml.safe_load`` the file (caller asserts it exists first)."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _triggers(workflow: dict) -> dict:
    """Return the workflow's trigger config, tolerating the ``on``/``True`` alias.

    PyYAML 1.1 maps a bare ``on:`` key to the boolean ``True``; both spellings
    appear in real workflow files. Fall back to the string ``"on"`` key.
    """
    return workflow.get("on") or workflow.get(True) or workflow.get("on") or {}


def test_workflow_yaml_parses() -> None:
    """``yaml.safe_load`` of the workflow file succeeds (valid YAML, top-level map)."""
    assert WORKFLOW.is_file(), f"missing workflow: {WORKFLOW}"
    data = _load(WORKFLOW)
    assert isinstance(data, dict)


def test_workflow_triggers_on_tags() -> None:
    """The workflow fires on tag push patterns matching ``v*`` (release.sh's tags)."""
    data = _load(WORKFLOW)
    push = _triggers(data).get("push") or {}
    tags = push.get("tags") or []
    assert isinstance(tags, list), f"on.push.tags is not a list: {tags!r}"
    assert any("v*" in str(t) for t in tags), (
        f"no 'v*' tag pattern in on.push.tags: {tags!r}"
    )


def test_workflow_has_oidc_permission() -> None:
    """OIDC trusted publishing needs ``id-token: write``; the Release step needs ``contents: write``.

    Both permissions may live at workflow level or on the publish job; assert
    they are present at one of those altitudes with the required value.
    """
    data = _load(WORKFLOW)

    # Collect permission blocks from workflow level + every job.
    perm_blocks: list[dict] = []
    if isinstance(data.get("permissions"), dict):
        perm_blocks.append(data["permissions"])
    jobs = data.get("jobs") or {}
    for job in jobs.values():
        if isinstance(job, dict) and isinstance(job.get("permissions"), dict):
            perm_blocks.append(job["permissions"])

    def _has(scope: str, value: str) -> bool:
        return any(str(p.get(scope)) == value for p in perm_blocks)

    assert _has("id-token", "write"), (
        f"permissions.id-token != 'write' at any level: {perm_blocks!r}"
    )
    assert _has("contents", "write"), (
        f"permissions.contents != 'write' at any level: {perm_blocks!r}"
    )


def test_workflow_uses_release_environment() -> None:
    """The publish job runs under the ``release`` environment (PyPI OIDC scope + protection)."""
    data = _load(WORKFLOW)
    jobs = data.get("jobs") or {}
    assert jobs, "workflow defines no jobs"
    envs = [
        str(job.get("environment"))
        for job in jobs.values()
        if isinstance(job, dict) and job.get("environment") is not None
    ]
    assert "release" in envs, (
        f"no job uses environment: 'release' (found {envs!r})"
    )


def test_workflow_supports_dry_run_dispatch() -> None:
    """A ``workflow_dispatch`` with a ``dry_run`` input rehearses build+guard without uploading."""
    data = _load(WORKFLOW)
    dispatch = _triggers(data).get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    assert "dry_run" in inputs, (
        f"workflow_dispatch.inputs.dry_run missing: {inputs!r}"
    )


def test_publish_steps_gated_on_push_and_ordered() -> None:
    """Regression guard for Fixes 1 & 2: publish/Release steps fire ONLY on a
    real tag push (``github.event_name == 'push'``), and the canonical
    ``jrag-cli`` publish precedes the ``java-codebase-rag`` shim publish.

    Parses the ordered ``jobs.<job>.steps`` list and asserts:
      - publish-root ("Publish root (jrag-cli)") precedes publish-shim
        ("Publish shim (java-codebase-rag)") — fixed root-then-shim order;
      - publish-root's ``if:`` references ``github.event_name`` (so a
        ``workflow_dispatch`` cannot publish) AND ``steps.root_check.outcome``
        (the idempotency gate);
      - publish-shim's ``if:`` references ``github.event_name`` AND
        ``steps.shim_check.outcome``;
      - the create-Release step's ``if:`` references ``github.event_name``.
    """
    data = _load(WORKFLOW)
    jobs = data.get("jobs") or {}
    assert jobs, "workflow defines no jobs"
    # Flatten the ordered steps list across jobs (one job here, but stay general).
    steps: list[dict] = []
    for job in jobs.values():
        if isinstance(job, dict):
            job_steps = job.get("steps") or []
            if isinstance(job_steps, list):
                steps.extend(s for s in job_steps if isinstance(s, dict))
    names = [str(s.get("name", "")) for s in steps]

    def _index(fragment: str) -> int:
        for i, name in enumerate(names):
            if fragment in name:
                return i
        raise AssertionError(
            f"no step name containing {fragment!r}; names={names!r}"
        )

    # (a) fixed root-then-shim publish order.
    root_idx = _index("Publish root")
    shim_idx = _index("Publish shim")
    assert root_idx < shim_idx, (
        f"publish-root (idx {root_idx}) must precede publish-shim "
        f"(idx {shim_idx}) in the ordered steps list; names={names!r}"
    )

    # (b) each publish step gates on event_name AND its idempotency outcome.
    root_if = str(steps[root_idx].get("if", ""))
    assert "github.event_name" in root_if, (
        f"publish-root if: must reference github.event_name: {root_if!r}"
    )
    assert "root_check.outcome" in root_if, (
        f"publish-root if: must reference steps.root_check.outcome: {root_if!r}"
    )

    shim_if = str(steps[shim_idx].get("if", ""))
    assert "github.event_name" in shim_if, (
        f"publish-shim if: must reference github.event_name: {shim_if!r}"
    )
    assert "shim_check.outcome" in shim_if, (
        f"publish-shim if: must reference steps.shim_check.outcome: {shim_if!r}"
    )

    # (c) create-Release gates on event_name.
    release_idx = _index("Create GitHub Release")
    release_if = str(steps[release_idx].get("if", ""))
    assert "github.event_name" in release_if, (
        f"create-Release if: must reference github.event_name: {release_if!r}"
    )


def test_notes_config_parses_and_categorizes() -> None:
    """``.github/release.yml`` parses; has categorized sections + a chore exclusion.

    Structural keys asserted (not formatting):
      - ``changelog.categories`` is a list of ``{title, labels}`` entries;
      - the section ``title``s include at minimum ``Features``, ``Bug Fixes``,
        and ``Documentation`` (the brief's floor);
      - an ``exclude.labels`` list (or branch/contributors filter) suppresses
        ``chore``-scoped PRs so they never appear in the generated notes.
  """
    assert NOTES.is_file(), f"missing notes config: {NOTES}"
    data = _load(NOTES)
    assert isinstance(data, dict)

    changelog = data.get("changelog")
    assert isinstance(changelog, dict), f"changelog block missing/invalid: {changelog!r}"

    categories = changelog.get("categories")
    assert isinstance(categories, list), f"changelog.categories not a list: {categories!r}"

    titles = {str(c.get("title")) for c in categories if isinstance(c, dict)}
    required = {"Features", "Bug Fixes", "Documentation"}
    missing = required - titles
    assert not missing, (
        f"changelog.categories missing required section title(s) {missing!r}; "
        f"found titles={sorted(titles)!r}"
    )

    # Each category that claims one of the required titles must carry labels.
    for cat in categories:
        if isinstance(cat, dict) and cat.get("title") in required:
            assert isinstance(cat.get("labels"), list) and cat["labels"], (
                f"category {cat.get('title')!r} has no labels: {cat!r}"
            )

    exclude = changelog.get("exclude") or {}
    assert isinstance(exclude, dict), f"changelog.exclude not a map: {exclude!r}"
    # chore suppression may be expressed as an excluded label, a branch filter,
    # or an excluded contributor — assert at least one suppression mechanism,
    # with label-based ``chore`` exclusion being the canonical form.
    suppressions = []
    if isinstance(exclude.get("labels"), list):
        suppressions.extend(str(x) for x in exclude["labels"])
    if isinstance(exclude.get("branches"), list):
        suppressions.extend(str(x) for x in exclude["branches"])
    if isinstance(exclude.get("contributors"), list):
        suppressions.extend(str(x) for x in exclude["contributors"])
    assert any("chore" in s for s in suppressions), (
        f"no chore suppression in changelog.exclude: {exclude!r}"
    )
