"""Password + Email-OTP authentication tests (signup, login 2FA, resend, reset)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud import auth, config, emails


class _FakeResult:
    def __init__(self, scalar=None, row=None):
        self._scalar = scalar
        self._row = row

    def scalar_one_or_none(self):
        return self._scalar

    def one(self):
        return self._row


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, state):
        self.state = state
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return _FakeTx()

    def add(self, obj):
        if obj.__class__.__name__ == "User":
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            self.state["users"][str(obj.email).lower()] = obj
        elif obj.__class__.__name__ == "EmailOtp":
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "attempts", None) is None:
                obj.attempts = 0
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            self.state["otps"].append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def get(self, model, pk):
        for u in self.state["users"].values():
            if u.id == pk:
                return u
        return None

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        if "pg_advisory_xact_lock" in sql:
            return _FakeResult()
        if "count(email_otps.id)" in sql:
            email = next((str(v).lower() for k, v in params.items() if "email" in k), None)
            ip = next((v for k, v in params.items() if "request_ip" in k), None)
            e_cnt = sum(1 for o in self.state["otps"] if o.email.lower() == email)
            ip_cnt = sum(1 for o in self.state["otps"] if ip and o.request_ip == ip)
            return _FakeResult(row=(e_cnt, ip_cnt))
        if sql.startswith("UPDATE email_otps"):
            email = next((str(v).lower() for k, v in params.items() if "email" in k), None)
            purpose = next((v for k, v in params.items() if "purpose" in k), None)
            for o in self.state["otps"]:
                if o.email.lower() == email and o.purpose == purpose and o.used_at is None:
                    o.used_at = datetime.now(timezone.utc)
            return _FakeResult()
        if "FROM email_otps" in sql:
            email = next((str(v).lower() for k, v in params.items() if "email" in k), None)
            purpose = next((v for k, v in params.items() if "purpose" in k), None)
            now = datetime.now(timezone.utc)
            matches = [
                o for o in self.state["otps"]
                if o.email.lower() == email
                and o.purpose == purpose
                and o.used_at is None
                and o.expires_at >= now
            ]
            return _FakeResult(scalar=matches[-1] if matches else None)
        if "FROM users" in sql:
            email = next((str(v).lower() for k, v in params.items() if "email" in k), None)
            return _FakeResult(scalar=self.state["users"].get(email))
        return _FakeResult()


def _setup(monkeypatch):
    state = {"users": {}, "otps": [], "sent": []}
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-otp-auth-32bytes")
    monkeypatch.setattr(auth.database, "session", lambda: _FakeSession(state))

    async def _fake_load(session, user_id):
        u = await session.get(auth.User, user_id)
        return auth.CurrentUser(id=u.id, email=u.email, entitled=True, plan="free")

    async def _fake_mx(email):
        return auth.email_policy.MX_OK

    async def _fake_send_otp(email, code, purpose="login"):
        state["sent"].append((email, code, purpose))

    async def _fake_denial(session, email):
        return None

    monkeypatch.setattr(auth, "_load_current_user", _fake_load)
    monkeypatch.setattr(auth.email_policy, "mx_verdict", _fake_mx)
    monkeypatch.setattr(emails, "send_otp_email", _fake_send_otp)
    monkeypatch.setattr(auth.evidence, "record_event", lambda **kw: None)
    monkeypatch.setattr("cloud.account.free_plan_denial_for_signup", _fake_denial)

    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app), state


def test_default_smtp_is_google(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert config.settings.smtp_host == "smtp.gmail.com"


def test_password_hash_roundtrip():
    h = auth.hash_password("CorrectHorse99!")
    assert h.startswith("scrypt$")
    assert auth.verify_password("CorrectHorse99!", h)
    assert not auth.verify_password("wrong-password", h)
    assert not auth.verify_password("CorrectHorse99!", None)


def test_signup_login_otp_and_reset_flow(monkeypatch):
    client, state = _setup(monkeypatch)

    # 1. Short password rejected
    r = client.post("/api/auth/signup", json={"email": "alice@gmail.com", "password": "short"})
    assert r.status_code == 400

    # 2. Signup sends OTP
    r = client.post("/api/auth/signup", json={"email": "alice@gmail.com", "password": "MyPassword123"})
    assert r.status_code == 200
    assert r.json()["otp_required"] is True
    assert len(state["sent"]) == 1
    _, signup_code, purpose = state["sent"][-1]
    assert purpose == "signup" and len(signup_code) == 6
    assert "alice@gmail.com" not in state["users"]

    # 3. Verify signup OTP creates user and returns JWT
    r = client.post("/api/auth/signup/verify", json={"email": "alice@gmail.com", "otp": signup_code})
    assert r.status_code == 200
    assert r.json()["token"]
    assert "alice@gmail.com" in state["users"]

    # 4. Login with wrong password fails
    r = client.post("/api/auth/login", json={"email": "alice@gmail.com", "password": "WrongPassword"})
    assert r.status_code == 401

    # 5. Login with right password sends OTP (no JWT yet)
    r = client.post("/api/auth/login", json={"email": "alice@gmail.com", "password": "MyPassword123"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "otp_required": True, "email": "alice@gmail.com"}
    _, login_code, purpose = state["sent"][-1]
    assert purpose == "login"

    # 6. Wrong OTP increments attempts and fails, right OTP succeeds
    r = client.post("/api/auth/login/verify", json={"email": "alice@gmail.com", "otp": "000000" if login_code != "000000" else "999999"})
    assert r.status_code == 400
    r = client.post("/api/auth/login/verify", json={"email": "alice@gmail.com", "otp": login_code})
    assert r.status_code == 200
    assert r.json()["token"]

    # 7. Password reset flow
    r = client.post("/api/auth/password-reset/request", json={"email": "alice@gmail.com"})
    assert r.status_code == 200
    _, reset_code, purpose = state["sent"][-1]
    assert purpose == "reset"
    r = client.post("/api/auth/password-reset/confirm", json={
        "email": "alice@gmail.com",
        "otp": reset_code,
        "new_password": "NewPassword456",
    })
    assert r.status_code == 200
    assert r.json()["token"]
    assert auth.verify_password("NewPassword456", state["users"]["alice@gmail.com"].password_hash)
