"""Identity vault client used by the application tier (tokenize at ingest, re-identify for display)."""

import httpx


class VaultError(Exception):
    pass


class VaultClient:
    def __init__(self, base_url: str, service_token: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=base_url, timeout=10.0, trust_env=False)
        self.headers = {"Authorization": f"Bearer {service_token}"}

    def tokenize(self, household_id: str, kind: str, value: str) -> str:
        r = self.http.post(f"/v1/households/{household_id}/tokens", json={"kind": kind, "value": value},
                           headers=self.headers)
        if r.status_code != 200:
            raise VaultError(f"vault tokenize failed: HTTP {r.status_code}")
        return r.json()["token"]

    def detokenize(self, household_id: str, token: str) -> tuple[str, str] | None:
        r = self.http.get(f"/v1/households/{household_id}/tokens/{token}", headers=self.headers)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise VaultError(f"vault detokenize failed: HTTP {r.status_code}")
        body = r.json()
        return body["kind"], body["value"]

    def entries(self, household_id: str) -> list[dict]:
        r = self.http.get(f"/v1/households/{household_id}/entries", headers=self.headers)
        if r.status_code != 200:
            raise VaultError(f"vault export failed: HTTP {r.status_code}")
        return r.json()["entries"]

    def delete_household(self, household_id: str) -> int:
        r = self.http.delete(f"/v1/households/{household_id}", headers=self.headers)
        if r.status_code != 200:
            raise VaultError(f"vault delete failed: HTTP {r.status_code}")
        return r.json()["deleted"]

    def healthy(self) -> bool:
        try:
            return self.http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
