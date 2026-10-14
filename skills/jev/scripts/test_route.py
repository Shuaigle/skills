"""Offline tests: no API key, network, or host-model switch is required."""

import copy
import io
import itertools
import json
import math
import socket
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import route


SECRET = "test-env-secret-please-never-echo"


def task():
    return {"host": "test-host", "task": "Rename a local variable",
            "models": [{"id": "fast", "description": "Fast model for simple tasks"},
                       {"id": "deep", "description": "Stronger reasoning for hard tasks"}],
            "current_model": "deep", "preference": "Prefer low latency"}


def answer():
    return {"model": "jev-1.13.0", "answers": {"model": {
        "type": "choice", "choice": "fast", "confidence": 0.81,
        "probabilities": {"fast": 0.88, "deep": 0.12}}},
        "usage": {"input_tokens": 318, "output_tokens": 34}}


def batch(scopes=("task", "skill", "subagent")):
    choices = {
        "task": [{"id": "task-fast", "description": "Fast for simple parent tasks"},
                 {"id": "task-deep", "description": "Deeper reasoning for parent tasks"}],
        "skill": [{"id": "test-first", "description": "Implement a feature using tests"}],
        "subagent": [{"id": "child-fast", "description": "Fast for small delegated tasks"},
                     {"id": "child-deep", "description": "Deeper reasoning for child tasks"}],
    }
    return {"host": "test-host", "task": "Check a delegated change",
            "decisions": {scope: choices[scope] for scope in scopes},
            "preference": "Prefer low latency"}


def batch_answer(data, selected=None):
    answers = {}
    for scope, options in data["decisions"].items():
        ids = [option["id"] for option in options]
        if scope == "skill":
            selected_skills = (selected or {}).get("skill", ids[:1])
            for index, skill_id in enumerate(ids):
                chosen = "select" if skill_id in selected_skills else "skip"
                answers[f"skill_{index}"] = {
                    "type": "choice", "choice": chosen, "confidence": 0.8,
                    "probabilities": {"select": 0.8 if chosen == "select" else 0.2,
                                      "skip": 0.8 if chosen == "skip" else 0.2},
                }
            continue
        chosen = (selected or {}).get(scope, ids[0])
        others = len(ids) - 1
        probabilities = {name: (0.8 if name == chosen else 0.2 / others)
                         for name in ids} if others else {chosen: 1.0}
        answers[scope] = {"type": "choice", "choice": chosen, "confidence": 0.8,
                          "probabilities": probabilities}
    return {"model": "jev-1.13.0", "answers": answers}


def response(status=200, body=None, retry_after=None):
    result = MagicMock()
    result.status = status
    result.getheader.return_value = retry_after
    result.read.return_value = json.dumps(answer() if body is None else body).encode()
    return result


class InputTests(unittest.TestCase):
    def test_missing_key_never_connects(self):
        with patch.dict(route.os.environ, {}, clear=True), patch.object(
                route.http.client, "HTTPSConnection") as connection:
            with self.assertRaisesRegex(route.RoutingError, "") as error:
                route.route(task())
            self.assertEqual(error.exception.code, "missing_api_key")
            connection.assert_not_called()

    def test_invalid_inputs_are_rejected(self):
        invalid = [None, {}, {**task(), "unknown": True}, {**task(), "models": []},
                   {**task(), "host": " "}, {**task(), "task": "task\nprivate"},
                   {**task(), "current_model": "unavailable"},
                   {**task(), "preference": None},
                   {**task(), "models": task()["models"] * 2},
                   {**task(), "models": [{"id": "fast", "description": ""}]},
                   {**task(), "models": [{"id": "fast", "description": "valid", "x": 1}]},
                   {**task(), "models": [{"id": str(i), "description": "model"}
                                         for i in range(256)]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(route.RoutingError):
                route.validate_input(value)

    def test_one_and_255_candidates_are_valid(self):
        for count in (1, 255):
            value = {**task(), "models": [{"id": str(i), "description": "model"}
                                          for i in range(count)], "current_model": "0"}
            self.assertEqual(len(route.validate_input(value)["model"]), count)


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(route.os.environ, {"JEV_API_KEY": SECRET}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.connection_patch = patch.object(route.http.client, "HTTPSConnection")
        self.factory = self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.connection = self.factory.return_value
        self.connection.getresponse.return_value = response()

    def test_real_request_shape_key_only_in_header(self):
        result = route.route(task())
        self.factory.assert_called_once()
        self.assertEqual(self.factory.call_args.args, ("api.typesafe.ai",))
        self.assertGreater(self.factory.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(self.factory.call_args.kwargs["timeout"], 15)
        self.assertEqual(self.connection.auto_open, 0)
        call = self.connection.request.call_args
        self.assertEqual(call.args, ("POST", "/v1/systemone"))
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer " + SECRET)
        self.assertNotIn(SECRET.encode(), call.kwargs["body"])
        payload = json.loads(call.kwargs["body"])
        self.assertEqual(payload["model"], "jev-latest")
        self.assertEqual(payload["state"], {key: task()[key] for key in (
            "host", "task", "current_model", "preference")})
        self.assertEqual(payload["questions"]["model"]["type"], "choice")
        self.assertEqual(payload["questions"]["model"]["criteria"], {
            "fast": task()["models"][0]["description"],
            "deep": task()["models"][1]["description"]})
        self.assertEqual(result, {"status": "recommended", "host": "test-host",
                                 "model": "fast", "confidence": 0.81,
                                 "probabilities": {"fast": 0.88, "deep": 0.12},
                                 "router_model": "jev-1.13.0"})
        self.connection.close.assert_called_once()

    def test_key_in_task_is_rejected_before_network(self):
        with self.assertRaises(route.RoutingError) as error:
            route.route({**task(), "task": SECRET})
        self.assertEqual(error.exception.code, "unsafe_input")
        self.factory.assert_not_called()

    def test_json_escaped_keys_are_rejected_in_every_request_field(self):
        for key in (SECRET + '"suffix', SECRET + '\\suffix'):
            values = []
            for field in ("host", "task", "preference"):
                values.append({**task(), field: "prefix " + key + " suffix"})
            value = task()
            value["models"][0]["description"] = "prefix " + key + " suffix"
            values.append(value)
            value = task()
            value["models"][0]["id"] = key
            values.append(value)
            value = task()
            value["models"][1]["id"] = key
            value["current_model"] = key
            values.append(value)
            for index, value in enumerate(values):
                with self.subTest(key_type=key[-7], field_index=index), patch.dict(
                        route.os.environ, {"JEV_API_KEY": key}):
                    with self.assertRaises(route.RoutingError) as error:
                        route.route(value)
                    self.assertEqual(error.exception.code, "unsafe_input")
        self.factory.assert_not_called()

    def test_redirect_is_rejected_without_following(self):
        self.connection.getresponse.return_value = response(302)
        with self.assertRaises(route.RoutingError) as error:
            route.route(task())
        self.assertEqual(error.exception.code, "http_error")
        self.connection.request.assert_called_once()

    def test_retry_is_bounded_and_retry_after_is_capped(self):
        self.connection.getresponse.return_value = response(429, retry_after="9999")
        with patch.object(route.Deadline, "wait") as sleep:
            with self.assertRaises(route.RoutingError) as error:
                route.route(task())
        self.assertEqual(error.exception.code, "http_error")
        self.assertEqual(self.connection.request.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 2])
        self.assertEqual(self.connection.close.call_count, 3)

    def test_overload_and_server_errors_retry_then_succeed(self):
        self.connection.getresponse.side_effect = [response(529), response(503), response()]
        with patch.object(route.Deadline, "wait") as sleep:
            self.assertEqual(route.route(task())["model"], "fast")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1])

    def test_authentication_error_does_not_retry_or_read_body(self):
        reply = response(401, {"error": SECRET})
        self.connection.getresponse.return_value = reply
        with self.assertRaises(route.RoutingError) as error:
            route.route(task())
        self.assertEqual(error.exception.code, "authentication_failed")
        self.connection.request.assert_called_once()
        reply.read.assert_not_called()

    def test_timeout_has_no_secret_and_closes_connection(self):
        self.connection.request.side_effect = TimeoutError(SECRET)
        with self.assertRaises(route.RoutingError) as error:
            route.route(task())
        self.assertEqual(error.exception.code, "network_error")
        self.assertNotIn(SECRET, str(error.exception))
        self.connection.close.assert_called_once()

    def test_oversized_or_non_json_response_is_rejected(self):
        for body in (b"x" * (route.MAX_BYTES + 1), b"not json " + SECRET.encode()):
            self.connection.getresponse.return_value.read.return_value = body
            with self.subTest(body_length=len(body)), self.assertRaises(
                    route.RoutingError) as error:
                route.route(task())
            self.assertEqual(error.exception.code, "invalid_response")


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(route.os.environ, {"JEV_API_KEY": SECRET}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_slow_body_obeys_whole_route_deadline(self):
        client, server = socket.socketpair()
        stop = threading.Event()
        finished = threading.Event()
        body = json.dumps(answer()).encode() + b" " * 1024

        class LocalConnection(route.http.client.HTTPConnection):
            closes = 0

            def connect(self):
                self.sock = client
                client.settimeout(self.timeout)

            def close(self):
                super().close()
                self.closes += 1
                # getresponse() first closes a Connection: close socket while
                # its response still owns the descriptor; finally closes again.
                if self.closes == 2:
                    finished.set()

        connection = LocalConnection("offline-test", timeout=0.04)

        def drip():
            try:
                server.sendall(("HTTP/1.1 200 OK\r\nConnection: close\r\n"
                                "Content-Length: %d\r\n\r\n" % len(body)).encode())
                for start in range(0, len(body), 8):
                    if stop.wait(0.005):
                        break
                    server.sendall(body[start:start + 8])
            except OSError:
                pass

        writer = threading.Thread(target=drip, daemon=True)
        writer.start()
        started = time.monotonic()
        try:
            with patch.dict(route.os.environ, {"JEV_API_KEY": SECRET}, clear=True), \
                    patch.object(route, "TIMEOUT", 0.04), \
                    patch.object(route.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(route.RoutingError) as error:
                    route.route(task())
            self.assertEqual(error.exception.code, "network_error")
            self.assertLess(time.monotonic() - started, 0.12)
            self.assertTrue(finished.wait(0.2))
            self.assertEqual(client.fileno(), -1)
        finally:
            stop.set()
            client.close()
            server.close()
            writer.join(0.5)

    def test_blocked_connect_returns_on_time_and_never_sends_later(self):
        client, server = socket.socketpair()
        release = threading.Event()
        closed = threading.Event()
        connection = MagicMock(sock=None)

        def connect():
            release.wait(0.5)
            connection.sock = client

        def close():
            client.close()
            closed.set()

        connection.connect.side_effect = connect
        connection.close.side_effect = close
        started = time.monotonic()
        try:
            with patch.object(route, "TIMEOUT", 0.04), patch.object(
                    route.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(route.RoutingError) as error:
                    route.route(task())
            self.assertEqual(error.exception.code, "network_error")
            self.assertLess(time.monotonic() - started, 0.12)
            connection.request.assert_not_called()
            self.assertEqual(connection.auto_open, 0)
            release.set()
            self.assertTrue(closed.wait(0.5))
            connection.request.assert_not_called()
            self.assertEqual(client.fileno(), -1)
        finally:
            release.set()
            client.close()
            server.close()

    def test_blocked_headers_cancel_active_socket_and_finish_worker(self):
        client, server = socket.socketpair()
        closed = threading.Event()

        class LocalConnection(route.http.client.HTTPConnection):
            def connect(self):
                self.sock = client

            def close(self):
                super().close()
                closed.set()

        connection = LocalConnection("offline-test")
        started = time.monotonic()
        try:
            with patch.object(route, "TIMEOUT", 0.04), patch.object(
                    route.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(route.RoutingError) as error:
                    route.route(task())
            self.assertEqual(error.exception.code, "network_error")
            self.assertLess(time.monotonic() - started, 0.12)
            self.assertTrue(closed.wait(0.5))
            self.assertEqual(client.fileno(), -1)
        finally:
            client.close()
            server.close()

    def test_retry_wait_cannot_outlive_remaining_deadline(self):
        connection = MagicMock()
        connection.getresponse.return_value = response(429, retry_after="2")
        started = time.monotonic()
        with patch.object(route, "TIMEOUT", 0.04), patch.object(
                route.http.client, "HTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(route.RoutingError) as error:
                route.route(task())
        self.assertEqual(error.exception.code, "network_error")
        self.assertLess(time.monotonic() - started, 0.12)
        factory.assert_called_once()
        connection.request.assert_called_once()

    def test_attempts_and_backoff_share_one_deadline(self):
        clock = [10.0]
        connection = MagicMock()

        def delayed_response():
            clock[0] += 0.02
            return response(429, retry_after="0.01")

        def backoff(deadline, delay):
            clock[0] += delay
            deadline.remaining()

        connection.getresponse.side_effect = delayed_response
        with patch.object(route, "TIMEOUT", 0.05), \
                patch.object(route.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(route.Deadline, "wait", autospec=True, side_effect=backoff), \
                patch.object(route.http.client, "HTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(route.RoutingError) as error:
                route.route(task())
        self.assertEqual(error.exception.code, "network_error")
        self.assertEqual(connection.request.call_count, 2)
        timeouts = [call.kwargs["timeout"] for call in factory.call_args_list]
        self.assertAlmostEqual(timeouts[0], 0.05)
        self.assertAlmostEqual(timeouts[1], 0.02)


class ResponseTests(unittest.TestCase):
    def test_response_rejects_bad_type_membership_and_distribution(self):
        variations = [None, [], {}, {**answer(), "model": SECRET}]
        changes = [
            {"type": "noul"}, {"choice": "unavailable"}, {"choice": "deep"},
            {"choice": []}, {"confidence": True}, {"confidence": math.nan},
            {"confidence": math.inf}, {"confidence": -0.1},
            {"probabilities": {"fast": 1}},
            {"probabilities": {"fast": 0.88, "deep": 0.12, "extra": 0}},
            {"probabilities": {"fast": 0.8, "deep": 0.8}},
            {"probabilities": {"fast": math.nan, "deep": 0.12}},
            {"probabilities": {"fast": True, "deep": 0}},
            {"probabilities": {"fast": 1.1, "deep": -0.1}},
        ]
        for change in changes:
            value = copy.deepcopy(answer())
            value["answers"]["model"].update(change)
            variations.append(value)
        for value in variations:
            with self.subTest(value=value), self.assertRaises(route.RoutingError) as error:
                route.validate_response(value, task(), route.validate_input(task()))
            self.assertEqual(error.exception.code, "invalid_response")

    def test_distribution_rounding_and_ties_are_allowed(self):
        value = answer()
        value["answers"]["model"]["probabilities"] = {"fast": 0.499, "deep": 0.499}
        self.assertEqual(route.validate_response(
            value, task(), route.validate_input(task()))["model"], "fast")


class BatchTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(route.os.environ, {"JEV_API_KEY": SECRET}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        connection_patch = patch.object(route.http.client, "HTTPSConnection")
        self.factory = connection_patch.start()
        self.addCleanup(connection_patch.stop)
        self.connection = self.factory.return_value

    def recommend(self, value, body=None):
        self.connection.getresponse.return_value = response(
            body=batch_answer(value) if body is None else body)
        return route.route(value)

    def test_selects_multiple_skills_in_one_request(self):
        value = batch(("skill",))
        value["decisions"]["skill"] = [
            {"id": "test-first", "description": "Implement a feature using tests"},
            {"id": "security", "description": "Check secret handling"},
            {"id": "slides", "description": "Create a presentation"},
        ]
        use = {"type": "choice", "choice": "select", "confidence": 0.8,
               "probabilities": {"select": 0.9, "skip": 0.1}}
        skip = {"type": "choice", "choice": "skip", "confidence": 0.6,
                "probabilities": {"select": 0.2, "skip": 0.8}}
        result = self.recommend(value, {"model": "jev-1.13.0", "answers": {
            "skill_0": use, "skill_1": use, "skill_2": skip}})
        self.assertEqual(result["decisions"]["skill"], {
            "choices": ["test-first", "security"],
            "evaluations": {
                "test-first": {"choice": "select", "confidence": 0.8,
                               "probabilities": {"select": 0.9, "skip": 0.1}},
                "security": {"choice": "select", "confidence": 0.8,
                             "probabilities": {"select": 0.9, "skip": 0.1}},
                "slides": {"choice": "skip", "confidence": 0.6,
                           "probabilities": {"select": 0.2, "skip": 0.8}},
            },
        })
        self.connection.request.assert_called_once()
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(set(payload["questions"]), {"skill_0", "skill_1", "skill_2"})
        for index, skill in enumerate(value["decisions"]["skill"]):
            question = payload["questions"][f"skill_{index}"]
            self.assertEqual(question["type"], "choice")
            self.assertEqual(question["instructions"]["skill"], skill)
            self.assertEqual(set(question["criteria"]), {"select", "skip"})

    def test_seven_scope_combinations_batch_only_selected_questions(self):
        scopes = ("task", "skill", "subagent")
        for count in range(1, 4):
            for selected in itertools.combinations(scopes, count):
                with self.subTest(scopes=selected):
                    self.factory.reset_mock()
                    value = batch(selected)
                    result = self.recommend(value)
                    self.connection.request.assert_called_once()
                    payload = json.loads(self.connection.request.call_args.kwargs["body"])
                    self.assertEqual(payload["model"], "jev-latest")
                    self.assertEqual(payload["state"], {
                        key: value[key] for key in ("host", "task", "preference")})
                    expected_questions = set(selected) - {"skill"}
                    if "skill" in selected:
                        expected_questions.add("skill_0")
                    self.assertEqual(set(payload["questions"]), expected_questions)
                    self.assertEqual(set(result), {
                        "status", "host", "router_model", "decisions"})
                    self.assertEqual(result["status"], "recommended")
                    self.assertEqual(result["host"], "test-host")
                    self.assertEqual(result["router_model"], "jev-1.13.0")
                    self.assertEqual(set(result["decisions"]), set(selected))
                    for scope in selected:
                        if scope == "skill":
                            self.assertEqual(result["decisions"]["skill"], {
                                "choices": ["test-first"],
                                "evaluations": {"test-first": {
                                    "choice": "select", "confidence": 0.8,
                                    "probabilities": {"select": 0.8, "skip": 0.2}}},
                            })
                            continue
                        question = payload["questions"][scope]
                        self.assertEqual(question["type"], "choice")
                        expected = {item["id"]: item["description"]
                                    for item in value["decisions"][scope]}
                        self.assertEqual(question["criteria"], expected)
                        reply = batch_answer(value)["answers"][scope]
                        self.assertEqual(result["decisions"][scope], {
                            key: reply[key] for key in ("choice", "confidence", "probabilities")})
                    self.factory.assert_called_once()

    def test_all_off_returns_disabled_without_key_or_network(self):
        with patch.dict(route.os.environ, {}, clear=True), patch.object(
                route.os.environ, "get", side_effect=AssertionError("No environment read allowed")):
            self.assertEqual(route.route(batch(())), {"status": "disabled"})
        self.factory.assert_not_called()

    def test_skipping_every_skill_returns_empty_choices(self):
        value = batch(("skill",))
        value["decisions"]["skill"].append({"id": "slides", "description": "Create slides"})
        result = self.recommend(value, batch_answer(value, {"skill": []}))
        self.assertEqual(result["decisions"]["skill"], {
            "choices": [],
            "evaluations": {
                "test-first": {"choice": "skip", "confidence": 0.8,
                               "probabilities": {"select": 0.2, "skip": 0.8}},
                "slides": {"choice": "skip", "confidence": 0.8,
                           "probabilities": {"select": 0.2, "skip": 0.8}},
            },
        })
        self.assertNotIn("model", result)

    def test_empty_skill_inventory_needs_no_credentials_or_network(self):
        value = batch(("skill",))
        value["decisions"]["skill"] = []
        with patch.dict(route.os.environ, {}, clear=True), patch.object(
                route.os.environ, "get", side_effect=AssertionError("No environment read allowed")):
            self.assertEqual(route.route(value), {
                "status": "recommended", "host": "test-host", "router_model": None,
                "decisions": {"skill": {"choices": [], "evaluations": {}}},
            })
        self.factory.assert_not_called()

    def test_empty_skills_still_routes_enabled_model_domains(self):
        value = batch()
        value["decisions"]["skill"] = []
        result = self.recommend(value)
        self.assertEqual(result["decisions"]["skill"], {"choices": [], "evaluations": {}})
        self.assertEqual(result["decisions"]["task"]["choice"], "task-fast")
        self.assertEqual(result["decisions"]["subagent"]["choice"], "child-fast")
        self.connection.request.assert_called_once()
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(set(payload["questions"]), {"task", "subagent"})

    def test_skill_ids_cannot_collide_with_question_ids_or_special_words(self):
        value = batch()
        value["decisions"]["skill"] = [
            {"id": name, "description": "An eligible optional workflow"}
            for name in ("task", "subagent", "skill_0", "__none__", "select", "skip")
        ]
        selected = ["task", "skill_0", "__none__", "skip"]
        body = batch_answer(value, {"skill": selected})
        body["answers"] = dict(reversed(list(body["answers"].items())))
        result = self.recommend(value, body)
        self.assertEqual(result["decisions"]["skill"]["choices"], selected)
        self.assertEqual(result["decisions"]["task"]["choice"], "task-fast")
        self.assertEqual(result["decisions"]["subagent"]["choice"], "child-fast")
        self.connection.request.assert_called_once()
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(set(payload["questions"]), {
            "task", "subagent", "skill_0", "skill_1", "skill_2", "skill_3", "skill_4", "skill_5"})
        self.assertEqual(payload["questions"]["skill_0"]["instructions"]["skill"]["id"], "task")
        self.assertEqual(payload["questions"]["skill_2"]["instructions"]["skill"]["id"], "skill_0")

    def test_child_summary_and_current_model_are_forwarded_when_applicable(self):
        value = batch(("subagent",))
        value["task"] = "Inspect only the child parser edge cases"
        self.recommend(value)
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(payload["state"]["task"], value["task"])
        self.assertNotIn("current_model", payload["state"])
        value = batch(("task", "skill"))
        value["current_model"] = "task-deep"
        self.recommend(value)
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(payload["state"]["current_model"], "task-deep")

    def test_invalid_scopes_candidates_and_current_model_never_connect(self):
        invalid = [
            {**batch(), "models": task()["models"]},
            {**batch(), "decisions": []},
            {**batch(), "decisions": {"unknown": []}},
            {**batch(), "decisions": {"TASK": task()["models"]}},
            {**batch(), "decisions": {"task": []}},
            {**batch(), "decisions": {"subagent": []}},
            {**batch(), "decisions": {"skill": batch()["decisions"]["skill"] * 2}},
            {**batch(), "decisions": {"skill": [{"id": "valid", "description": ""}]}},
            {**batch(), "decisions": {"skill": [{"id": "", "description": "valid"}]}},
            {**batch(), "decisions": {"skill": None}},
            {**batch(("skill",)), "current_model": "task-fast"},
            {**batch(("subagent",)), "current_model": "child-fast"},
            {**batch(()), "current_model": "task-fast"},
            {**batch(), "current_model": "child-fast"},
            {**batch(()), "host": ""},
            {**batch(()), "task": ""},
            {**batch(()), "preference": ""},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(route.RoutingError) as error:
                route.route(value)
            self.assertEqual(error.exception.code, "invalid_input")
        self.factory.assert_not_called()

    def test_scope_candidate_bounds(self):
        for scope, minimum, maximum in (("task", 1, 255), ("subagent", 1, 255),
                                         ("skill", 0, 254)):
            for count in (minimum, maximum, maximum + 1):
                with self.subTest(scope=scope, count=count):
                    value = batch((scope,))
                    value["decisions"][scope] = [{"id": str(i), "description": "Available"}
                                                  for i in range(count)]
                    if count > maximum:
                        with self.assertRaises(route.RoutingError) as error:
                            route.route(value)
                        self.assertEqual(error.exception.code, "invalid_input")
                    else:
                        self.factory.reset_mock()
                        result = self.recommend(value)
                        self.assertEqual(set(result["decisions"]), {scope})
                        if scope == "skill" and count == 0:
                            self.factory.assert_not_called()
                            continue
                        payload = json.loads(self.connection.request.call_args.kwargs["body"])
                        if scope == "skill":
                            self.assertEqual(len(payload["questions"]), count)
                            self.assertEqual(len(result["decisions"]["skill"]["evaluations"]), count)
                        else:
                            self.assertEqual(len(payload["questions"][scope]["criteria"]), count)

    def test_response_requires_each_requested_scope_and_its_exact_choices(self):
        value = batch()
        value["decisions"]["skill"].append({"id": "security", "description": "Check secrets"})
        original = batch_answer(value)
        variations = []
        for scope in original["answers"]:
            missing = copy.deepcopy(original)
            del missing["answers"][scope]
            variations.append(missing)
            for change in ({"choice": "other-domain"}, {"confidence": True},
                           {"probabilities": {"unknown": 1}},
                           {"type": "text"}, {"choice": "__none__"}):
                changed = copy.deepcopy(original)
                changed["answers"][scope].update(change)
                variations.append(changed)
        extra = copy.deepcopy(original)
        extra["answers"]["model"] = answer()["answers"]["model"]
        variations.append(extra)
        obsolete = copy.deepcopy(original)
        del obsolete["answers"]["skill_0"]
        del obsolete["answers"]["skill_1"]
        obsolete["answers"]["skill"] = {
            "type": "choice", "choice": "test-first", "confidence": 0.8,
            "probabilities": {"test-first": 0.8, "security": 0.1, "__none__": 0.1},
        }
        variations.append(obsolete)
        cross = copy.deepcopy(original)
        cross["answers"]["task"] = original["answers"]["subagent"]
        variations.append(cross)
        for body in variations:
            with self.subTest(body=body), self.assertRaises(route.RoutingError) as error:
                self.recommend(value, body)
            self.assertEqual(error.exception.code, "invalid_response")

    def test_batch_key_guard_checks_ids_and_descriptions_before_serializing(self):
        for key in (SECRET + '"suffix', SECRET + '\\suffix'):
            for scope in ("task", "skill", "subagent"):
                for field in ("id", "description"):
                    value = batch((scope,))
                    value["decisions"][scope][0][field] = "prefix " + key + " suffix"
                    with self.subTest(scope=scope, field=field), patch.dict(
                            route.os.environ, {"JEV_API_KEY": key}):
                        with self.assertRaises(route.RoutingError) as error:
                            route.route(value)
                        self.assertEqual(error.exception.code, "unsafe_input")
        self.factory.assert_not_called()


class CliTests(unittest.TestCase):
    def run_cli(self, raw, error=None):
        output = io.StringIO()
        stdin = MagicMock(buffer=io.BytesIO(raw))
        with patch.object(route.sys, "stdin", stdin), redirect_stdout(output):
            if error is None:
                with patch.dict(route.os.environ, {}, clear=True):
                    code = route.main([])
            else:
                with patch.object(route, "route", side_effect=error):
                    code = route.main([])
        return code, output.getvalue()

    def test_cli_never_prints_input_or_exception_contents(self):
        for error in (None, ValueError(SECRET), route.RoutingError("network_error")):
            code, output = self.run_cli(json.dumps(task()).encode(), error)
            self.assertEqual(code, 1)
            self.assertNotIn(SECRET, output)
            self.assertNotIn(task()["task"], output)
            self.assertEqual(json.loads(output)["status"], "error")

    def test_cli_rejects_malformed_and_oversized_json(self):
        for raw in (b"bad json", b" " * (route.MAX_BYTES + 1)):
            code, output = self.run_cli(raw)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output), {"status": "error", "code": "invalid_input"})

    def test_unknown_cli_arguments_are_redacted(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(route.main(["--api-key", SECRET]), 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "error", "code": "invalid_arguments"})
        self.assertNotIn(SECRET, output.getvalue())

    def test_cli_disabled_is_success_without_key(self):
        code, output = self.run_cli(json.dumps(batch(())).encode())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {"status": "disabled"})

    def test_cli_rejects_duplicate_decision_names(self):
        raw = (b'{"host":"test-host","task":"test",'
               b'"decisions":{"skill":[],"skill":[]}}')
        with patch.object(route.http.client, "HTTPSConnection") as connection:
            code, output = self.run_cli(raw)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), {"status": "error", "code": "invalid_input"})
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
