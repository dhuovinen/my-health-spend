"""UX-09 (ADR-055): the getting-started checklist follows the records, so it resumes where the member left off."""

from mhs.core import onboarding
from mhs.core.reconcile import Dataset


def keys_left(ds, first=None):
    return [s.key for s in onboarding.steps(ds, 2026, "/uploads", first) if not s.done]


def test_tc_ux_09_1_first_run_lists_every_step_in_order():
    assert keys_left(Dataset()) == ["members", "plan", "terms", "account", "document", "result"]


def test_tc_ux_09_2_resumes_at_the_step_left():
    ds = Dataset(members=[{"id": "m", "name": "M"}],
                 plans=[{"id": "p", "plan_year": 2026, "insurer": "X",
                         "limits": [{"type": "deductible", "network": "in_network", "level": "individual",
                                     "amount": 1}]}])
    assert keys_left(ds) == ["terms", "account", "document", "result"]
    ds.plans[0]["terms_confirmed"] = True
    ds.accounts = [{"id": "hsa", "name": "HSA", "type": "hsa"}]
    ds.documents = [{"id": "d", "type": "eob"}]
    assert keys_left(ds, "v1") == []
    assert onboarding.remaining(onboarding.steps(ds, 2026, "/uploads", "v1")) == 0
