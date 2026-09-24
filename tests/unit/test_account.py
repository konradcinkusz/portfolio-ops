"""The account scan's adapter (spec §7.12, ADR 0008), against a scripted GitHub.

Every name here is invented. The real client runs — URL building, JSON, error mapping —
and only the socket is replaced.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from helpers import TODAY, FakeGitHub
from portfolio_ops.account import read_account, utc_date
from portfolio_ops.model import ACCOUNT_TOKEN, NOT_SCANNED, Account, AccountRepository

TOKEN = "github_pat_example_not_a_real_token"  # noqa: S105 — invented
LOGIN = "example-owner"
REPOS = "/user/repos?affiliation=owner&per_page=100&page=1"


def repo(
    name: str,
    pushed_at: str | None = "2026-09-20T10:00:00Z",
    *,
    private: bool = True,
    fork: bool = False,
    archived: bool = False,
) -> dict[str, Any]:
    return {
        "full_name": f"{LOGIN}/{name}",
        "private": private,
        "fork": fork,
        "archived": archived,
        "pushed_at": pushed_at,
    }


def activity(name: str) -> str:
    return f"/repos/{LOGIN}/{name}/activity?actor={LOGIN}&direction=desc&per_page=1"


def github(*repositories: dict[str, Any]) -> FakeGitHub:
    return (
        FakeGitHub()
        .on("GET", "/user", body={"login": LOGIN})
        .on("GET", REPOS, body=list(repositories))
    )


def scan(
    fake: FakeGitHub,
    *,
    token: str = TOKEN,
    listed: frozenset[str] = frozenset(),
    left_out: str | None = None,
    hide_private: bool = False,
) -> Account:
    return read_account(
        {ACCOUNT_TOKEN: token},
        fake,
        today=TODAY,
        listed=listed,
        left_out=left_out,
        hide_private=hide_private,
    )


def test_without_a_token_nothing_is_asked() -> None:
    fake = FakeGitHub()

    account = read_account(
        {}, fake, today=TODAY, listed=frozenset(), left_out=None, hide_private=False
    )

    assert account == NOT_SCANNED
    assert not account.failed
    assert fake.requests == []


def test_a_classic_token_is_refused_before_anything_is_sent() -> None:
    fake = FakeGitHub()

    account = scan(fake, token="ghp_example_classic_token")  # noqa: S106 — invented

    assert account.failed
    assert account.scan is None
    assert "is a classic personal access token, which cannot be read-only" in account.problem
    assert fake.requests == []


def test_candidates_are_the_repositories_pushed_in_the_window() -> None:
    fake = github(
        repo("alpha"),  # pushed in the window: a candidate
        repo("old", "2026-09-14T23:59:59Z"),  # the day before the window
        repo("first-day", "2026-09-15T00:00:00Z"),  # the window's first day
        repo("never", None),
        repo("shelved", archived=True),
        repo("upstream-fix", fork=True),  # a fork no product lists
        repo("own-fork", fork=True),  # a fork that repos lists
    )
    for name in ("alpha", "first-day", "own-fork"):
        fake.on("GET", activity(name), body=[{"timestamp": "2026-09-19T08:00:00Z"}])

    account = scan(fake, listed=frozenset({f"{LOGIN}/own-fork"}))

    assert account.scan is not None
    assert account.scan.login == LOGIN
    assert (account.scan.since, account.scan.until) == (dt.date(2026, 9, 15), TODAY)
    by_name = {r.name.split("/")[1]: r for r in account.scan.repositories}
    assert {n for n, r in by_name.items() if r.activity == "read"} == {
        "alpha",
        "first-day",
        "own-fork",
    }
    assert by_name["alpha"].owner_active_on == dt.date(2026, 9, 19)
    assert by_name["old"] == AccountRepository(
        f"{LOGIN}/old", True, False, False, dt.date(2026, 9, 14)
    )
    assert by_name["never"].pushed_on is None
    assert [p for p in fake.paths() if "/activity" in p] == [
        activity("alpha"),
        activity("first-day"),
        activity("own-fork"),
    ]


def test_the_owners_activity_is_asked_for_by_login_and_a_bot_push_is_not_it() -> None:
    fake = github(repo("beta", "2026-09-21T06:00:00Z"))
    fake.on("GET", activity("beta"), body=[])  # only Dependabot pushed

    account = scan(fake)

    assert account.scan is not None
    (beta,) = account.scan.repositories
    assert (beta.activity, beta.owner_active_on) == ("read", None)


def test_the_token_goes_in_a_header_and_never_in_a_url() -> None:
    fake = github(repo("alpha"))
    fake.on("GET", activity("alpha"), body=[])

    scan(fake)

    assert fake.requests
    for request in fake.requests:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in request.url
        assert request.method == "GET"


def test_the_data_repository_is_left_out() -> None:
    fake = github(repo("alpha"), repo("Portfolio-Data"))
    fake.on("GET", "/repos/example-owner/alpha/activity", body=[])

    account = scan(fake, left_out=f"{LOGIN}/portfolio-data")

    assert account.scan is not None
    assert [r.name for r in account.scan.repositories] == [f"{LOGIN}/alpha"]
    assert account.scan.left_out == f"{LOGIN}/portfolio-data"
    assert not any("Portfolio-Data" in p for p in fake.paths())


def test_hide_private_is_carried_to_the_rules() -> None:
    account = scan(github(), hide_private=True)

    assert account.scan is not None
    assert account.scan.hide_private


def test_every_page_of_repositories_is_read() -> None:
    first = [repo(f"r{n:03}", "2026-01-01T00:00:00Z") for n in range(100)]
    fake = github()
    fake.on("GET", REPOS, body=first)
    page_2 = "/user/repos?affiliation=owner&per_page=100&page=2"
    fake.on("GET", page_2, body=[repo("last", "2026-01-02T00:00:00Z")])

    account = scan(fake)

    assert account.scan is not None
    assert len(account.scan.repositories) == 101
    assert account.scan.repositories[-1].name == f"{LOGIN}/last"


def test_an_unreadable_activity_list_falls_back_to_the_push_and_says_why() -> None:
    fake = github(repo("alpha"), repo("beta"))
    fake.on(
        "GET",
        "/repos/example-owner/alpha/activity",
        status=403,
        body={"message": "Resource not accessible by personal access token"},
        headers={"x-accepted-github-permissions": "contents=read"},
    )
    fake.on("GET", "/repos/example-owner/beta/activity", status=404, body={})

    account = scan(fake)

    assert account.scan is not None
    assert [r.activity for r in account.scan.repositories] == ["unreadable", "unreadable"]
    assert account.scan.unreadable == (
        "the token cannot read the repositories' activity lists (HTTP 403; GitHub asks for "
        "contents=read)"
    )


def test_an_odd_answer_about_one_repository_leaves_only_that_one_to_the_push_date() -> None:
    fake = github(repo("empty"), repo("alpha"))
    fake.on("GET", "/repos/example-owner/empty/activity", 409, {"message": "Repository is empty"})
    fake.on("GET", activity("alpha"), body=[{"timestamp": "2026-09-19T08:00:00Z"}])

    account = scan(fake)

    assert account.scan is not None
    assert [r.activity for r in account.scan.repositories] == ["unreadable", "read"]
    assert account.scan.unreadable == (
        "GitHub did not return the activity list of example-owner/empty (HTTP 409)"
    )


def test_a_token_revoked_during_the_scan_stops_it() -> None:
    fake = github(repo("alpha"))
    fake.on("GET", "/repos/example-owner/alpha/activity", 401, {"message": "Bad credentials"})

    account = scan(fake)

    assert account.failed
    assert account.problem.startswith("GitHub rejected PORTFOLIO_ACCOUNT_TOKEN (HTTP 401)")


@pytest.mark.parametrize(
    ("status", "headers", "message"),
    [
        (
            401,
            {},
            (
                f"GitHub rejected {ACCOUNT_TOKEN} (HTTP 401): it has expired or been revoked — "
                "create a new fine-grained token and replace the secret"
            ),
        ),
        (
            403,
            {"x-ratelimit-remaining": "0"},
            "the token's GitHub rate limit is spent — the next run scans again",
        ),
        (429, {}, "the token's GitHub rate limit is spent — the next run scans again"),
        (
            403,
            {},
            (
                "the token may not list the account's repositories (GET /user returned HTTP "
                "403: Forbidden) — give it access to all repositories, with the read-only "
                "Metadata permission"
            ),
        ),
        (500, {}, "GET /user returned HTTP 500: Forbidden — the next run scans again"),
    ],
)
def test_a_failed_scan_says_why_and_how_to_fix_it(
    status: int, headers: dict[str, str], message: str
) -> None:
    fake = FakeGitHub().on("GET", "/user", status, {"message": "Forbidden"}, headers)

    account = scan(fake)

    assert account.failed
    assert account.scan is None
    assert account.problem == message
    assert TOKEN not in account.problem


def test_a_rate_limit_hit_during_the_activity_reads_stops_the_scan() -> None:
    fake = github(repo("alpha"))
    fake.on("GET", "/repos/example-owner/alpha/activity", 429, {"message": "slow down"})

    account = scan(fake)

    assert account.failed
    assert "rate limit is spent" in account.problem


def test_a_network_failure_says_github_could_not_be_reached() -> None:
    fake = FakeGitHub().fail("GET", "/user", OSError("connection refused"))

    account = scan(fake)

    assert account.failed
    assert account.problem.startswith("GitHub could not be reached: GET /user failed: ")
    assert account.problem.endswith(" — the next run scans again")


@pytest.mark.parametrize(
    ("stamp", "day"),
    [
        ("2026-09-21T23:30:00Z", dt.date(2026, 9, 21)),
        ("2026-09-21T23:30:00-02:00", dt.date(2026, 9, 22)),
        ("2026-09-22T01:00:00+03:00", dt.date(2026, 9, 21)),
        ("2026-09-21T12:00:00", dt.date(2026, 9, 21)),
        ("not a time", None),
        ("", None),
        (None, None),
    ],
)
def test_github_timestamps_become_utc_dates(stamp: str | None, day: dt.date | None) -> None:
    assert utc_date(stamp) == day


def test_entries_github_did_not_describe_fully_are_skipped() -> None:
    fake = github(repo("alpha", "2026-01-01T00:00:00Z"), {"name": "no-full-name"}, "garbage")

    account = scan(fake)

    assert account.scan is not None
    assert [r.name for r in account.scan.repositories] == [f"{LOGIN}/alpha"]


def test_an_activity_entry_without_a_timestamp_is_no_activity() -> None:
    fake = github(repo("alpha"))
    fake.on("GET", activity("alpha"), body=[{"activity_type": "push"}])

    account = scan(fake)

    assert account.scan is not None
    assert account.scan.repositories[0].activity == "read"
    assert account.scan.repositories[0].owner_active_on is None


# ------------------------------------------------------------------ coverage (§7.12, r4)


def test_a_token_that_does_not_list_the_private_data_repository_sees_no_private_one() -> None:
    fake = github(repo("public-tool", "2026-01-01T00:00:00Z", private=False))

    account = scan(fake, left_out=f"{LOGIN}/portfolio-data")

    assert account.scan is not None
    assert not account.scan.sees_private


@pytest.mark.parametrize(
    ("repositories", "left_out", "hide_private"),
    [
        # the data repository is listed: the token sees private repositories
        ([repo("portfolio-data", "2026-01-01T00:00:00Z")], f"{LOGIN}/portfolio-data", False),
        # another private repository is listed: the token was given some of them
        ([repo("secret", "2026-01-01T00:00:00Z")], f"{LOGIN}/portfolio-data", False),
        # the data repository belongs to another owner: nothing to tell
        ([repo("public-tool", "2026-01-01T00:00:00Z", private=False)], "an-org/data", False),
        # no data repository is known: nothing to tell
        ([repo("public-tool", "2026-01-01T00:00:00Z", private=False)], None, False),
        # allow_public: the data repository may be public, so its absence tells nothing
        ([repo("public-tool", "2026-01-01T00:00:00Z", private=False)], f"{LOGIN}/data", True),
    ],
)
def test_without_that_proof_the_token_is_taken_to_see_private_repositories(
    repositories: list[dict[str, Any]], left_out: str | None, hide_private: bool
) -> None:
    account = scan(github(*repositories), left_out=left_out, hide_private=hide_private)

    assert account.scan is not None
    assert account.scan.sees_private
