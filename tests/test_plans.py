from pathlib import Path

from scripts.preservation.plans import PlanStore, create_plan


def test_plan_is_stable_and_atomic_metadata(tmp_path: Path) -> None:
    plan = create_plan("src", "fingerprint", "zip", "aminet", ("util/a.lha",), "members-only")
    store = PlanStore(tmp_path / "metadata")
    path = store.save(plan)
    loaded = store.load(plan.id)
    assert loaded.fingerprint == plan.fingerprint
    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
