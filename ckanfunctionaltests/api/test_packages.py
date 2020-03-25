import re
from warnings import warn

from dmtestutils.comparisons import AnySupersetOf

from ckanfunctionaltests.api import validate_against_schema


def test_package_list(base_url, rsession):
    response = rsession.get(f"{base_url}/action/package_list")
    assert response.status_code == 200
    validate_against_schema(response.json(), "package_list")

    assert response.json()["success"] is True


def test_package_show_404(base_url, rsession):
    response = rsession.get(f"{base_url}/action/package_show?id=plates-knives-and-forks")
    assert response.status_code == 404

    assert response.json()["success"] is False


def test_package_show(subtests, base_url, rsession, random_pkg_slug):
    response = rsession.get(f"{base_url}/action/package_show?id={random_pkg_slug}")
    assert response.status_code == 200
    rj = response.json()

    with subtests.test("response validity"):
        validate_against_schema(rj, "package_show")
        assert rj["success"] is True
        assert rj["result"]["name"] == random_pkg_slug
        assert all(res["package_id"] == rj['result']['id'] for res in rj["result"]["resources"])

    with subtests.test("uuid lookup consistency"):
        # we should be able to look up this same package by its uuid and get an identical response
        uuid_response = rsession.get(f"{base_url}/action/package_show?id={rj['result']['id']}")
        assert uuid_response.status_code == 200
        assert uuid_response.json() == rj

    with subtests.test("organization consistency"):
        org_response = rsession.get(
            f"{base_url}/action/organization_show?id={rj['result']['organization']['id']}"
        )
        assert org_response.status_code == 200
        assert org_response.json()["result"] == AnySupersetOf(rj['result']['organization'])


def test_package_search_by_full_slug_general_term(subtests, base_url, rsession, random_pkg_slug):
    response = rsession.get(
        f"{base_url}/action/package_search?q={random_pkg_slug}&rows=100"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    desired_result = tuple(
        pkg for pkg in response.json()["result"]["results"] if pkg["name"] == random_pkg_slug
    )
    assert desired_result
    if len(desired_result) > 1:
        warn(f"Multiple results ({len(desired_result)}) with name = {random_pkg_slug!r})")

    with subtests.test("approx consistency with package_show"):
        ps_response = rsession.get(f"{base_url}/action/package_show?id={random_pkg_slug}")
        assert ps_response.status_code == 200
        assert any(ps_response.json()["result"]["id"] == result["id"] for result in desired_result)

        # TODO assert actual contents are approximately equal (exact equality is out the window)


def test_package_search_by_revision_id_specific_field(subtests, base_url, rsession, random_pkg):
    response = rsession.get(
        f"{base_url}/action/package_search?fq=revision_id:{random_pkg['revision_id']}"
        "&rows=1000"
    )
    assert response.status_code == 200
    rj = response.json()
    assert rj["success"] is True

    desired_result = tuple(
        pkg for pkg in rj["result"]["results"] if pkg["id"] == random_pkg["id"]
    )
    assert len(desired_result) == 1

    with subtests.test("all results match criteria"):
        assert all(
            random_pkg["revision_id"] == pkg["revision_id"] for pkg in rj["result"]["results"]
        )

    with subtests.test("approx consistency with package_show"):
        assert random_pkg["name"] == desired_result[0]["name"]
        assert random_pkg["organization"] == desired_result[0]["organization"]
        # TODO assert actual contents are approximately equal (exact equality is out the window)


_all_alpha_re = re.compile(r"[a-z]+", re.I)


def _extract_search_terms(source_text: str, n: int) -> str:
    """
    choose n longest "clean" words from the source_text as our search terms (longer words
    are more likely to be distinctive) and format them for use in a url
    """
    return "+".join(sorted(
        (token for token in source_text.split() if _all_alpha_re.fullmatch(token)),
        key=lambda t: len(t),
        reverse=True,
    )[:n])


def test_package_search_by_org_id_specific_field_and_title_general_term(
    subtests,
    base_url,
    rsession,
    random_pkg,
):
    title_terms = _extract_search_terms(random_pkg["title"], 2)

    response = rsession.get(
        f"{base_url}/action/package_search?fq=owner_org:{random_pkg['owner_org']}"
        f"&q={title_terms}&rows=1000"
    )
    assert response.status_code == 200
    rj = response.json()
    assert rj["success"] is True

    with subtests.test("all results match criteria"):
        assert all(
            random_pkg["owner_org"] == pkg["owner_org"] for pkg in rj["result"]["results"]
        )
        # we can't reliably test for the search terms because they may have been stemmed
        # and not correspond to exact matches

    desired_result = tuple(
        pkg for pkg in rj["result"]["results"] if pkg["id"] == random_pkg["id"]
    )
    if rj["result"]["count"] > 1000 and not desired_result:
        # we don't have all results - it may well be on a latter page
        warn(f"Expected package {random_pkg['id']!r} not found on first page of results")
    else:
        assert len(desired_result) == 1

        with subtests.test("approx consistency with package_show"):
            assert random_pkg["name"] == desired_result[0]["name"]
            assert random_pkg["organization"] == desired_result[0]["organization"]
            # TODO assert actual contents are approximately equal (exact equality is out the window)


def test_package_search_facets(subtests, base_url, rsession, random_pkg):
    notes_terms = _extract_search_terms(random_pkg["notes"], 2)

    response = rsession.get(
        f"{base_url}/action/package_search?q={notes_terms}&rows=10"
        "&facet.field=[\"license_id\",\"organization\"]&facet.limit=-1"
    )
    assert response.status_code == 200
    rj = response.json()
    assert rj["success"] is True

    with subtests.test("facets include random_pkg's value"):
        assert random_pkg["organization"]["name"] in rj["result"]["facets"]["organization"]
        assert any(
            random_pkg["organization"]["name"] == val["name"]
            for val in rj["result"]["search_facets"]["organization"]["items"]
        )

        # not all packages have a license_id
        if random_pkg.get("license_id"):
            assert random_pkg["license_id"] in rj["result"]["facets"]["license_id"]
            assert any(
                random_pkg["license_id"] == val["name"]
                for val in rj["result"]["search_facets"]["license_id"]["items"]
            )
