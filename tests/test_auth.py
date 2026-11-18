import re

from app.utility import mail
from tests.conftest import PASSWORD


def register(client, email="new@example.com", username="newbie", password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "username": username, "password": password})


def login(client, email, password=PASSWORD, **extra):
    return client.post("/auth/login", json={"email": email, "password": password, **extra})


def test_register_signs_in_and_normalizes_email(client):
    res = register(client, email="  New@Example.COM ")
    assert res.status_code == 201
    assert res.get_json()["user"]["email"] == "new@example.com"
    assert client.get("/api/me").get_json()["username"] == "newbie"


def test_session_endpoint_never_401s(client, make_user):
    assert client.get("/auth/session").get_json() == {"user": None}
    make_user("alice")
    login(client, "alice@example.com")
    user = client.get("/auth/session").get_json()["user"]
    assert user["username"] == "alice" and user["email"] == "alice@example.com"


def test_register_validation(client, make_user):
    make_user("alice")
    assert register(client, email="not-an-email").status_code == 400
    assert register(client, username="x").status_code == 400
    assert register(client, username="no spaces").status_code == 400
    assert register(client, password="short").status_code == 400
    assert register(client, email="alice@example.com").status_code == 409
    assert register(client, username="ALICE").status_code == 400  # usernames are case-insensitive


def test_auth_endpoints_reject_form_posts(client):
    res = client.post("/auth/login", data={"email": "a@b.co", "password": PASSWORD})
    assert res.status_code == 415


def test_login_logout(client, make_user):
    make_user("alice")
    wrong = login(client, "alice@example.com", "wrong password")
    unknown = login(client, "nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()  # no hint about which accounts exist

    assert login(client, "ALICE@example.com").status_code == 200
    assert client.get("/api/me").status_code == 200
    client.post("/auth/logout", json={})
    assert client.get("/api/me").status_code == 401


def test_login_can_issue_tokens_for_api_clients(client, make_user):
    make_user("alice")
    body = login(client, "alice@example.com", tokens=True).get_json()
    other = client.application.test_client()  # no cookie
    assert other.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200

    refreshed = other.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.get_json()


def test_forgot_password_does_not_reveal_accounts(client, make_user):
    make_user("alice")
    unknown = client.post("/auth/forgot", json={"email": "nobody@example.com"})
    known = client.post("/auth/forgot", json={"email": "alice@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.get_json() == known.get_json()
    assert len(mail.outbox) == 1
    assert mail.outbox[0]["To"] == "alice@example.com"


def _reset_token_from_outbox():
    body = mail.outbox[-1].get_content()
    match = re.search(r"https://wayl\.test/reset\?token=(\S+)", body)
    assert match, body
    return match.group(1)


def test_password_reset_flow(client, make_user, auth):
    alice = make_user("alice")
    old_token = auth(alice)

    # another browser that is signed in before the reset
    other = client.application.test_client()
    login(other, "alice@example.com")
    assert other.get("/api/me").status_code == 200

    client.post("/auth/forgot", json={"email": "alice@example.com"})
    token = _reset_token_from_outbox()

    assert client.post("/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    res = client.post("/auth/reset", json={"token": token, "password": "a brand new password"})
    assert res.status_code == 200
    assert client.get("/api/me").status_code == 200  # signed in after the reset

    # the link works only once, and everything issued before the reset stops working
    again = client.post("/auth/reset", json={"token": token, "password": "another new password"})
    assert again.status_code == 400
    assert client.get("/api/me", headers=old_token).status_code == 401
    assert other.get("/api/me").status_code == 401

    fresh = client.application.test_client()
    assert login(fresh, "alice@example.com").status_code == 401
    assert login(fresh, "alice@example.com", "a brand new password").status_code == 200


def test_reset_rejects_garbage_tokens(client):
    assert client.post("/auth/reset", json={"token": "nope", "password": PASSWORD}).status_code == 400
    assert client.post("/auth/reset", json={"password": PASSWORD}).status_code == 400


def test_change_password(client, make_user, auth):
    alice = make_user("alice")
    headers = auth(alice)
    bad = client.post("/api/me/password", json={"current_password": "nope", "new_password": "whatever123"},
                      headers=headers)
    assert bad.status_code == 403
    ok = client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "whatever123"},
                     headers=headers)
    assert ok.status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401  # old token revoked
    assert login(client.application.test_client(), "alice@example.com", "whatever123").status_code == 200


def test_bad_and_wrong_type_tokens_are_rejected(client, make_user):
    from app.utility import create_jwt

    user = make_user("alice")
    assert client.get("/api/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    refresh = create_jwt(user, refresh=True)
    assert client.get("/api/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_refresh_token_must_be_the_stored_one(client, make_user):
    from app.utility import create_jwt

    user = make_user("alice")
    token = create_jwt(user, 3600, refresh=True)
    assert client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_cookie_session_writes_require_json(client, make_user):
    make_user("alice")
    login(client, "alice@example.com")
    form = client.post("/api/playlists", data={"name": "x"})  # what a cross-site form would send
    assert form.status_code == 415
    assert client.post("/api/playlists", json={"name": "x"}).status_code == 201


def test_rate_limit_on_login(client, make_user):
    make_user("alice")
    codes = [login(client, "alice@example.com", "wrong").status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
