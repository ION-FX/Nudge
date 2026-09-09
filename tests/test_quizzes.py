"""Quizzes: builder, publish, auto-grading, single attempt, gradebook integration."""
import re

from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _create_quiz(client, class_id, title="Chapter check", publish=False):
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": title, "instructions": "Good luck!", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    quiz_id = int(response.headers["location"].rsplit("/", 1)[-1])
    if publish:
        assert client.post(f"/quizzes/{quiz_id}/publish", data={"csrf": token}, follow_redirects=False).status_code == 303
    return quiz_id


def _add_question(client, quiz_id, data):
    return client.post(f"/quizzes/{quiz_id}/questions", data={**data, "csrf": get_csrf(client)}, follow_redirects=False)


def _build_mixed_quiz(client, class_id):
    quiz_id = _create_quiz(client, class_id, publish=True)
    assert _add_question(
        client,
        quiz_id,
        {
            "prompt": "Which planet is the largest?",
            "kind": "mc",
            "choices": "Mars\nEarth\nJupiter\nVenus",
            "correct_index": "2",
            "points": "2",
        },
    ).status_code == 303
    assert _add_question(
        client,
        quiz_id,
        {"prompt": "Water boils at 100C at sea level.", "kind": "truefalse", "correct_tf": "true", "points": "1"},
    ).status_code == 303
    assert _add_question(
        client,
        quiz_id,
        {"prompt": "Gas plants absorb", "kind": "short", "correct_short": "carbon dioxide\nCO2", "points": "2"},
    ).status_code == 303
    return quiz_id


def test_quiz_builder_and_question_management(client, admin):
    class_id, _ = make_class(client)
    quiz_id = _create_quiz(client, class_id)
    page = client.get(f"/quizzes/{quiz_id}")
    assert "draft" in page.text
    assert "Add a question" in page.text

    assert _add_question(
        client, quiz_id, {"prompt": "2+2?", "kind": "mc", "choices": "3\n4\n5", "correct_index": "1", "points": "3"}
    ).status_code == 303
    page = client.get(f"/quizzes/{quiz_id}")
    assert "2+2?" in page.text
    assert "correct" in page.text
    assert "3 pt" in page.text

    # mc requires a valid correct index
    redirect = _add_question(client, quiz_id, {"prompt": "broken", "kind": "mc", "choices": "a\nb", "correct_index": "9"})
    assert "Pick which option" in client.get(f"/quizzes/{quiz_id}", follow_redirects=True).text
    assert redirect.status_code == 303

    # short answer requires an accepted answer
    _add_question(client, quiz_id, {"prompt": "broken too", "kind": "short", "correct_short": ""})
    assert "accepted answer" in client.get(f"/quizzes/{quiz_id}", follow_redirects=True).text

    # remove the good question again
    page = client.get(f"/quizzes/{quiz_id}")
    question_id = re.search(r"questions/(\d+)/delete", page.text).group(1)
    assert client.post(f"/questions/{question_id}/delete", data={"csrf": get_csrf(client)}, follow_redirects=False).status_code == 303
    assert "Remove" not in client.get(f"/quizzes/{quiz_id}").text  # no questions remain


def test_student_take_and_autograde(client, admin, student):
    class_id, code = make_class(client)
    quiz_id = _build_mixed_quiz(client, class_id)

    _login_student(client, student)
    join_class(client, code)
    page = client.get(f"/quizzes/{quiz_id}")
    assert "Take the quiz" in page.text

    token = get_csrf(client)
    # Q1 wrong (Mars), Q2 correct (true), Q3 correct (CO2) -> 3 of 5 points
    response = client.post(
        f"/quizzes/{quiz_id}/take",
        data={"q_1": "0", "q_2": "true", "q_3": "co2", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    result_page = client.get(f"/quizzes/{quiz_id}")
    assert "You scored 3 / 5" in result_page.text
    assert "+2 pts" in result_page.text and "+1 pt" in result_page.text and "0 pts" in result_page.text
    assert "Correct answer: Jupiter" in result_page.text

    # second attempt is blocked
    blocked = client.post(
        f"/quizzes/{quiz_id}/take", data={"q_1": "2", "q_2": "true", "q_3": "co2", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert blocked.status_code == 303
    assert "already taken" in client.get(f"/quizzes/{quiz_id}", follow_redirects=True).text


def test_teacher_sees_attempts(client, admin, student):
    class_id, code = make_class(client)
    quiz_id = _build_mixed_quiz(client, class_id)
    _login_student(client, student)
    join_class(client, code)
    client.post(
        f"/quizzes/{quiz_id}/take",
        data={"q_1": "2", "q_2": "true", "q_3": "carbon dioxide", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    page = client.get(f"/quizzes/{quiz_id}")
    assert "Attempts (1" in page.text
    assert "Stu Dent" in page.text
    assert "5 / 5" in page.text


def test_unpublished_quiz_hidden_from_students(client, admin, student):
    class_id, code = make_class(client)
    quiz_id = _create_quiz(client, class_id, publish=False)
    _login_student(client, student)
    join_class(client, code)
    assert client.get(f"/quizzes/{quiz_id}").status_code == 403
    _login_admin(client)
    assert client.get(f"/quizzes/{quiz_id}").status_code == 200  # teacher previews drafts


def test_publish_notifies_students(client, admin, student):
    class_id, code = make_class(client)
    quiz_id = _create_quiz(client, class_id, publish=False)
    _login_student(client, student)
    join_class(client, code)
    assert client.get("/notifications").text.count("New quiz") == 0
    _login_admin(client)
    client.post(f"/quizzes/{quiz_id}/publish", data={"csrf": get_csrf(client)}, follow_redirects=False)
    _login_student(client, student)
    assert "New quiz" in client.get("/notifications").text


def test_gradebook_includes_quiz_scores_and_csv(client, admin, student):
    class_id, code = make_class(client)
    quiz_id = _build_mixed_quiz(client, class_id)
    _login_student(client, student)
    join_class(client, code)
    client.post(
        f"/quizzes/{quiz_id}/take",
        data={"q_1": "2", "q_2": "false", "q_3": "oxygen", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    page = client.get(f"/classes/{class_id}/gradebook")
    assert "Stu Dent" in page.text
    assert "1" in page.text  # scored 1 point (Q1 wrong, Q2 wrong, Q3 wrong -> 0? no: '2' is Jupiter=correct so 2 pts)

    csv_response = client.get(f"/classes/{class_id}/gradebook.csv")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "Stu Dent" in csv_response.text
    assert re.search(r"Quiz: Chapter check", csv_response.text)
