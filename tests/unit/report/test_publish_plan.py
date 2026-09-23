"""R1 (§7.5, AC8): one open weekly-review issue, kept current by a pure planner."""

from __future__ import annotations

import json

import pytest

from helpers import FakeGitHub
from portfolio_ops.github import GitHubClient, Issue, Request, Response
from portfolio_ops.report.publish import LABEL, MAX_BODY, Plan, issue_body, plan, publish
from portfolio_ops.report.render import Rendered

REPO = "owner/data"
ISSUES = f"/repos/{REPO}/issues"


def issue(number: int, created: str) -> Issue:
    return Issue(number, "Weekly review — week of 2026-09-14", f"{created}T07:00:00Z")


# ------------------------------------------------------------------ the planner


def test_no_open_issue_and_items_creates_one() -> None:
    assert plan([], has_items=True) == Plan(create=True)


def test_one_open_issue_and_items_updates_it() -> None:
    assert plan([issue(7, "2026-09-14")], has_items=True) == Plan(update=7)


def test_open_issues_and_no_items_closes_them_all() -> None:
    open_issues = [issue(7, "2026-09-14"), issue(9, "2026-09-15")]

    assert plan(open_issues, has_items=False) == Plan(close=(7, 9))


def test_several_open_issues_and_items_update_the_oldest_and_close_the_rest() -> None:
    open_issues = [issue(12, "2026-09-20"), issue(7, "2026-09-14"), issue(9, "2026-09-14")]

    assert plan(open_issues, has_items=True) == Plan(update=7, close=(9, 12))


def test_no_open_issue_and_no_items_does_nothing() -> None:
    assert plan([], has_items=False) == Plan()


@pytest.mark.parametrize("open_count", [0, 1, 2, 5])
@pytest.mark.parametrize("has_items", [True, False])
def test_after_a_plan_exactly_one_issue_is_open_while_there_are_items(
    open_count: int, has_items: bool
) -> None:
    the_plan = plan([issue(n, f"2026-09-{10 + n:02d}") for n in range(open_count)], has_items)

    left_open = open_count + the_plan.create - len(the_plan.close)

    assert left_open == (1 if has_items else 0)


# ------------------------------------------------------------------ the executor


def rendered(has_items: bool = True, markdown: str = "# Weekly review\n") -> Rendered:
    return Rendered("Weekly review — week of 2026-09-21", markdown, has_items)


def run(
    github: FakeGitHub, *, with_token: bool = True, dry_run: bool = False, items: bool = True
) -> tuple[Plan, list[str]]:
    said: list[str] = []
    the_plan = publish(
        rendered=rendered(items),
        repository=REPO,
        token="t" if with_token else None,
        transport=github,
        api_url="https://api.github.com",
        dry_run=dry_run,
        say=said.append,
    )
    return the_plan, said


def body(request: Request) -> dict[str, object]:
    assert request.body is not None
    parsed: dict[str, object] = json.loads(request.body)
    return parsed


def test_creating_an_issue_creates_the_missing_label_first() -> None:
    github = FakeGitHub().on("GET", ISSUES, body=[])
    github.on("POST", f"/repos/{REPO}/labels", status=201, body={"name": LABEL})
    github.on("POST", ISSUES, status=201, body={"number": 3})

    _, said = run(github)

    assert [(r.method, r.url.split(".com")[1].split("?")[0]) for r in github.writes] == [
        ("POST", f"/repos/{REPO}/labels"),
        ("POST", ISSUES),
    ]
    assert body(github.writes[1]) == {
        "title": "Weekly review — week of 2026-09-21",
        "body": "# Weekly review\n",
        "labels": [LABEL],
    }
    assert said[-1] == f"published: created issue #3 in {REPO}"


def test_an_existing_label_is_not_created_again() -> None:
    github = FakeGitHub().on("GET", ISSUES, body=[])
    github.on("GET", f"/repos/{REPO}/labels/{LABEL}", body={"name": LABEL})
    github.on("POST", ISSUES, status=201, body={"number": 3})

    run(github)

    assert [r.method for r in github.writes] == ["POST"]


def test_updating_rewrites_the_title_and_body_of_the_open_issue() -> None:
    open_issue = {"number": 7, "title": "old", "created_at": "2026-09-14T07:00:00Z"}
    github = FakeGitHub().on("GET", ISSUES, body=[open_issue])
    github.on("PATCH", f"{ISSUES}/7", body={"number": 7})

    run(github)

    (request,) = github.writes
    assert request.method == "PATCH"
    assert body(request) == {
        "title": "Weekly review — week of 2026-09-21",
        "body": "# Weekly review\n",
    }


def test_closing_marks_the_issues_completed() -> None:
    open_issues = [
        {"number": 7, "title": "a", "created_at": "2026-09-14T07:00:00Z"},
        {"number": 9, "title": "b", "created_at": "2026-09-15T07:00:00Z"},
    ]
    github = FakeGitHub().on("GET", ISSUES, body=open_issues)
    github.on("PATCH", f"{ISSUES}/7", body={}).on("PATCH", f"{ISSUES}/9", body={})

    the_plan, _ = run(github, items=False)

    assert the_plan == Plan(close=(7, 9))
    assert [body(r) for r in github.writes] == [
        {"state": "closed", "state_reason": "completed"}
    ] * 2


def test_pull_requests_carrying_the_label_are_not_issues() -> None:
    items = [
        {"number": 4, "title": "a PR", "created_at": "2026-09-01T07:00:00Z", "pull_request": {}},
        {"number": 7, "title": "the review", "created_at": "2026-09-14T07:00:00Z"},
    ]
    github = FakeGitHub().on("GET", ISSUES, body=items).on("PATCH", f"{ISSUES}/7", body={})

    the_plan, _ = run(github)

    assert the_plan == Plan(update=7)


def test_a_dry_run_reads_but_sends_no_write_request() -> None:
    github = FakeGitHub().on("GET", ISSUES, body=[])

    the_plan, said = run(github, dry_run=True)

    assert the_plan == Plan(create=True)
    assert github.writes == []
    assert {r.method for r in github.requests} == {"GET"}
    assert said[0].startswith('dry run: planned action: create issue "Weekly review — week of')
    assert "the weekly-review label is missing and would be created first" in said[0]
    assert "no write request was sent" in said[1]


def test_a_dry_run_without_a_token_assumes_no_open_issue_and_says_so() -> None:
    github = FakeGitHub()

    the_plan, said = run(github, with_token=False, dry_run=True)

    assert the_plan == Plan(create=True)
    assert github.requests == []
    assert said[0] == f"no GITHUB_TOKEN: assuming {REPO} has no open weekly-review issue"


def test_a_body_too_long_for_github_is_truncated_with_a_note() -> None:
    long = rendered(markdown="x" * (MAX_BODY + 10))

    text = issue_body(long)

    assert len(text) < 65_536
    assert text.endswith("run `portfolio-ops report` for all of it.*\n")


def test_open_issues_are_read_page_by_page() -> None:
    pages = {
        1: [
            {"number": n, "title": "t", "created_at": f"2026-09-01T00:00:{n % 60:02d}Z"}
            for n in range(100)
        ],
        2: [{"number": 100, "title": "t", "created_at": "2026-09-02T00:00:00Z"}],
    }
    seen: list[str] = []

    def transport(request: Request) -> Response:
        seen.append(request.url)
        page = int(request.url.rsplit("page=", 1)[1])
        return Response(200, json.dumps(pages[page]).encode())

    issues = GitHubClient(transport, "t").open_issues(REPO, LABEL)

    assert len(issues) == 101
    assert len(seen) == 2
    assert "labels=weekly-review" in seen[0]
