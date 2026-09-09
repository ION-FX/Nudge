"""Tests for material text extraction, upload validation and lifecycle."""
import io
import re

from app.extract import ext_of, extract_text
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, get_csrf, join_class, login, login_as, logout, make_class


def test_ext_of():
    assert ext_of("notes.TXT") == ".txt"
    assert ext_of("a.b.c.pdf") == ".pdf"
    assert ext_of("noext") == ""


def test_extract_text_files():
    assert extract_text("a.txt", b"hello world") == "hello world"
    assert extract_text("a.md", b"# Heading\n\nBody") == "# Heading\n\nBody"
    assert extract_text("a.csv", b"a,b\n1,2\n") == "a,b\n1,2"
    assert extract_text("a.py", b"print('hi')\n") == "print('hi')"


def test_extract_replaces_bad_utf8():
    text = extract_text("a.txt", b"\xff\xfe bad bytes ok")
    assert "bad bytes ok" in text


def test_extract_binary_types_return_empty():
    assert extract_text("a.png", b"\x89PNG\r\n") == ""
    assert extract_text("a.docx", b"PK\x03\x04") == ""


def test_extract_truncates_to_cap():
    big = ("x" * 50000).encode()
    assert len(extract_text("big.txt", big)) == 20000


def test_upload_requires_login(client):
    response = client.post("/classes/1/materials/new", data={"title": "x"}, follow_redirects=False)
    assert response.status_code == 303  # bounced to login


def test_upload_and_ai_readable_badge(client, admin, student):
    class_id, code = make_class(client)
    assert join_class(client, code).status_code == 303
    login_as(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/materials/new",
        data={
            "title": "Reading",
            "description": "week 1",
            "pasted_text": "The mitochondria is the powerhouse of the cell.",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/classes/{class_id}")
    assert "Reading" in page.text
    assert "Nudge can read this" in page.text


def test_upload_file_and_download(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Notes", "csrf": token},
        files={"file": ("notes.txt", io.BytesIO(b"chapter one"), "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/classes/{class_id}")
    material_id = re.search(r"materials/(\d+)", page.text).group(1)
    download = client.get(f"/materials/{material_id}/file")
    assert download.status_code == 200
    assert b"chapter one" in download.content


def test_upload_rejects_bad_extension(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Bad", "csrf": token},
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "allowed" in response.text and ".exe" in response.text


def test_edit_material_title_and_text(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Old", "pasted_text": "old text", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}")
    material_id = re.search(r"materials/(\d+)", page.text).group(1)
    response = client.post(
        f"/materials/{material_id}/edit",
        data={"title": "New title", "pasted_text": "brand new text", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "New title" in client.get(f"/materials/{material_id}").text
    assert "brand new text" in client.get(f"/materials/{material_id}").text


def test_delete_material(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Doomed", "pasted_text": "bye", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}")
    material_id = re.search(r"materials/(\d+)", page.text).group(1)
    response = client.post(f"/materials/{material_id}/delete", data={"csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get(f"/materials/{material_id}").status_code == 404


def test_outsider_blocked_from_material(client, admin, student):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Secret", "pasted_text": "classified", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    logout(client)
    login(client, student["email"], student["password"])
    response = client.get("/materials/1", follow_redirects=False)
    assert response.status_code == 403
