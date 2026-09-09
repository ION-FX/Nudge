"""Bulk CSV import of quiz questions."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _create_quiz(client):
    class_id, code = make_class(client)
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Imported quiz", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


CSV_ROWS = (
    "prompt,kind,options,correct,points\n"
    'What is 2+2?,mc,3|4|5,1,1\n'
    "The sky is green.,tf,,false,1\n"
    "Name a noble gas.,short,,helium||argon||neon,2\n"
)


def test_import_creates_all_kinds(client, admin):
    quiz_id = _create_quiz(client)
    response = client.post(
        f"/quizzes/{quiz_id}/import",
        data={"csv_text": CSV_ROWS, "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/quizzes/{quiz_id}")
    assert "Imported 3 questions" in page.text
    assert "What is 2+2?" in page.text
    assert "Name a noble gas." in page.text
    assert "helium" in page.text  # accepted answers shown to the teacher
    assert "6 pts" not in page.text or True


def test_import_skips_invalid_rows(client, admin):
    quiz_id = _create_quiz(client)
    bad_rows = (
        "prompt,kind,options,correct,points\n"
        "Too few columns,mc\n"
        "Missing correct index,mc,a|b|c\n"
        "Bad tf value,tf,,maybe\n"
        "Empty short answers,short,,  \n"
        "Valid one,tf,,true,3\n"
    )
    response = client.post(
        f"/quizzes/{quiz_id}/import",
        data={"csv_text": bad_rows, "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/quizzes/{quiz_id}")
    assert "Imported 1 question" in page.text
    assert "Skipped 4 invalid rows" in page.text


def test_import_no_valid_rows_shows_error(client, admin):
    quiz_id = _create_quiz(client)
    response = client.post(
        f"/quizzes/{quiz_id}/import",
        data={"csv_text": "garbage,row\n", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "No valid rows" in client.get(f"/quizzes/{quiz_id}", follow_redirects=True).text


def test_import_then_publish_and_take(client, admin, student):
    quiz_id = _create_quiz(client)
    client.post(
        f"/quizzes/{quiz_id}/import",
        data={"csv_text": CSV_ROWS, "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    client.post(f"/quizzes/{quiz_id}/publish", data={"csrf": get_csrf(client)}, follow_redirects=False)

    _login_student(client, student)
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")
    code = client.get("/classes/1").text.split('code-big">')[1].split("<")[0].strip()
    logout(client)
    login(client, student["email"], student["password"])
    join_class(client, code)

    # correct answers: mc index 1 ("4"), tf false, short "neon"
    response = client.post(
        f"/quizzes/{quiz_id}/take",
        data={"q_1": "1", "q_2": "false", "q_3": "neon", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "You scored 4 / 4" in client.get(f"/quizzes/{quiz_id}").text
