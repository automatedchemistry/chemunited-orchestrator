from chemunited.qt.project.recent import RecentProjectsStore


def test_recent_projects_store_keeps_newest_unique_paths(tmp_path):
    store = RecentProjectsStore(tmp_path / "recent_projects.json", limit=2)
    first = tmp_path / "first.chemunited"
    second = tmp_path / "second.chemunited"
    third = tmp_path / "third.chemunited"

    store.add(first)
    store.add(second)
    store.add(first)

    assert store.list() == [first.resolve(), second.resolve()]

    store.add(third)

    assert store.list() == [third.resolve(), first.resolve()]


def test_recent_projects_store_prunes_missing_paths(tmp_path):
    store = RecentProjectsStore(tmp_path / "recent_projects.json")
    existing = tmp_path / "existing.chemunited"
    missing = tmp_path / "missing.chemunited"
    existing.write_text("", encoding="utf-8")

    store.add(existing)
    store.add(missing)

    assert store.prune_missing() == [existing.resolve()]
    assert store.list() == [existing.resolve()]


def test_recent_projects_store_ignores_corrupt_json(tmp_path):
    path = tmp_path / "recent_projects.json"
    path.write_text("{", encoding="utf-8")

    assert RecentProjectsStore(path).list() == []
