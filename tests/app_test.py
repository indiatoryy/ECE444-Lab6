import json

import pytest
from pathlib import Path

from project.app import app, db

TEST_DB = "test.db"


@pytest.fixture
def client():
    BASE_DIR = Path(__file__).resolve().parent.parent
    test_uri = f"sqlite:///{BASE_DIR.joinpath(TEST_DB)}"
    original_database = app.config["DATABASE"]
    original_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    app.config["TESTING"] = True
    app.config["DATABASE"] = BASE_DIR.joinpath(TEST_DB)
    app.config["SQLALCHEMY_DATABASE_URI"] = test_uri

    with app.app_context():
        # Flask-SQLAlchemy 3 creates the engine at startup, so the config
        # change above does not move an existing connection on its own.
        original_engine = db.engines[None]
        db.session.remove()
        db.engines[None] = db._make_engine(None, {"url": test_uri}, app)
        db.create_all()  # setup
        yield app.test_client()  # tests run here
        db.session.remove()
        db.drop_all()  # teardown
        db.engines[None].dispose()
        db.engines[None] = original_engine
        app.config["DATABASE"] = original_database
        app.config["SQLALCHEMY_DATABASE_URI"] = original_uri


def login(client, username, password):
    """Login helper function"""
    return client.post(
        "/login",
        data=dict(username=username, password=password),
        follow_redirects=True,
    )


def logout(client):
    """Logout helper function"""
    return client.get("/logout", follow_redirects=True)


def test_index(client):
    response = client.get("/", content_type="html/text")
    assert response.status_code == 200


def test_database(client):
    """initial test. ensure that the database exists"""
    tester = Path("test.db").is_file()
    assert tester


def test_empty_db(client):
    """Ensure database is blank"""
    rv = client.get("/")
    assert b"No entries yet. Add some!" in rv.data


def test_login_logout(client):
    """Test login and logout using helper functions"""
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"])
    assert b"You were logged in" in rv.data
    rv = logout(client)
    assert b"You were logged out" in rv.data
    rv = login(client, app.config["USERNAME"] + "x", app.config["PASSWORD"])
    assert b"Invalid username" in rv.data
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"] + "x")
    assert b"Invalid password" in rv.data


def test_messages(client):
    """Ensure that user can post messages"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.post(
        "/add",
        data=dict(title="<Hello>", text="<strong>HTML</strong> allowed here"),
        follow_redirects=True,
    )
    assert b"No entries here so far" not in rv.data
    assert b"<Hello>" in rv.data
    assert b"<strong>HTML</strong> allowed here" in rv.data


def test_delete_message(client):
    """Ensure the messages are being deleted"""
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 0
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 1


def test_search(client):
    """Ensure search shows only posts that match the query"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    client.post(
        "/add",
        data=dict(title="Hello", text="first entry"),
        follow_redirects=True,
    )
    client.post(
        "/add",
        data=dict(title="Other", text="second entry"),
        follow_redirects=True,
    )

    rv = client.get("/search/")
    assert rv.status_code == 200

    rv = client.get("/search/?query=hello")
    assert b"Hello" in rv.data
    assert b"first entry" in rv.data
    assert b"Other" not in rv.data
    assert b"second entry" not in rv.data

    rv = client.get("/search/?query=SECOND")
    assert b"Other" in rv.data
    assert b"second entry" in rv.data
    assert b"Hello" not in rv.data
