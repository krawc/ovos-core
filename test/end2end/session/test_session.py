import time
from time import sleep
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager, Session

from ..minicroft import get_minicroft


class TestSessions(TestCase):

    def setUp(self):
        self.skill_id = "skill-ovos-hello-world.openvoiceos"
        self.core = get_minicroft(self.skill_id)

    def tearDown(self) -> None:
        self.core.stop()

    def test_no_session(self):
        SessionManager.sessions = {}
        SessionManager.default_session = SessionManager.sessions["default"] = Session("default")
        SessionManager.default_session.lang = "en-us"
        SessionManager.default_session.pipeline = [
            "adapt_high"
        ]

        messages = []

        def new_msg(msg):
            nonlocal messages
            m = Message.deserialize(msg)
            if m.msg_type in ["ovos.skills.settings_changed"]:
                return  # skip these, only happen in 1st run
            messages.append(m)
            print(len(messages), msg)

        def wait_for_n_messages(n):
            nonlocal messages
            t = time.time()
            while len(messages) < n:
                sleep(0.1)
                if time.time() - t > 10:
                    raise RuntimeError("did not get the number of expected messages under 10 seconds")

        self.core.bus.on("message", new_msg)

        utt = Message("recognizer_loop:utterance",
                      {"utterances": ["hello world"]})
        self.core.bus.emit(utt)

        # confirm all expected messages are sent
        expected_messages = [
            "recognizer_loop:utterance",  # no session
            f"{self.skill_id}:HelloWorldIntent",
            "mycroft.skill.handler.start",
            "intent.service.skills.activate",
            "intent.service.skills.activated",
            f"{self.skill_id}.activate",
            "ovos.session.update_default",
            "enclosure.active_skill",
            "speak",
            "mycroft.skill.handler.complete",
            "ovos.session.update_default"
        ]
        wait_for_n_messages(len(expected_messages))

        self.assertEqual(len(expected_messages), len(messages))

        for idx, m in enumerate(messages):
            self.assertEqual(m.msg_type, expected_messages[idx])

        # verify that "session" and "lang" is injected
        # (missing in utterance message) and kept in all messages
        for m in messages[1:]:
            self.assertEqual(m.context["session"]["session_id"], "default")
            self.assertEqual(m.context["lang"], "en-us")

        # verify intent triggers
        self.assertEqual(messages[1].msg_type, f"{self.skill_id}:HelloWorldIntent")
        self.assertEqual(messages[1].data["intent_type"], f"{self.skill_id}:HelloWorldIntent")
        # verify skill_id is now present in every message.context
        for m in messages[1:]:
            self.assertEqual(m.context["skill_id"], self.skill_id)

        # verify intent
        self.assertEqual(messages[2].msg_type, "mycroft.skill.handler.start")
        self.assertEqual(messages[2].data["name"], "HelloWorldSkill.handle_hello_world_intent")
        # verify skill is activated
        self.assertEqual(messages[3].msg_type, "intent.service.skills.activate")
        self.assertEqual(messages[3].data["skill_id"], self.skill_id)
        self.assertEqual(messages[4].msg_type, "intent.service.skills.activated")
        self.assertEqual(messages[4].data["skill_id"], self.skill_id)
        self.assertEqual(messages[5].msg_type, f"{self.skill_id}.activate")
        self.assertEqual(messages[6].msg_type, "ovos.session.update_default")
        # verify intent code execution
        self.assertEqual(messages[7].msg_type, "enclosure.active_skill")
        self.assertEqual(messages[7].data["skill_id"], self.skill_id)
        self.assertEqual(messages[8].msg_type, "speak")
        self.assertEqual(messages[8].data["lang"], "en-us")
        self.assertFalse(messages[8].data["expect_response"])
        self.assertEqual(messages[8].data["meta"]["dialog"], "hello.world")
        self.assertEqual(messages[8].data["meta"]["skill"], self.skill_id)
        # intent complete
        self.assertEqual(messages[9].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[9].data["name"], "HelloWorldSkill.handle_hello_world_intent")

        # verify default session is now updated
        self.assertEqual(messages[10].msg_type, "ovos.session.update_default")
        self.assertEqual(messages[10].data["session_data"]["session_id"], "default")
        # test deserialization of payload
        sess = Session.deserialize(messages[10].data["session_data"])
        self.assertEqual(sess.session_id, "default")

        # test that active skills list has been updated
        self.assertEqual(sess.active_skills[0][0], self.skill_id)
        self.assertEqual(messages[10].data["session_data"]["active_skills"][0][0], self.skill_id)

    def test_explicit_default_session(self):
        SessionManager.sessions = {}
        SessionManager.default_session = SessionManager.sessions["default"] = Session("default")
        SessionManager.default_session.lang = "en-us"
        now = time.time()
        SessionManager.default_session.active_skills = [(self.skill_id, now)]
        SessionManager.default_session.pipeline = [
            "converse",
            "adapt_high"
        ]

        messages = []

        def new_msg(msg):
            nonlocal messages
            m = Message.deserialize(msg)
            if m.msg_type in ["ovos.skills.settings_changed"]:
                return  # skip these, only happen in 1st run
            messages.append(m)
            print(len(messages), msg)

        def wait_for_n_messages(n):
            nonlocal messages
            t = time.time()
            while len(messages) < n:
                sleep(0.1)
                if time.time() - t > 10:
                    raise RuntimeError("did not get the number of expected messages under 10 seconds")

        self.core.bus.on("message", new_msg)

        utt = Message("recognizer_loop:utterance",
                      {"utterances": ["hello world"]},
                      {"session": SessionManager.default_session.serialize(),  # explicit
                       "xxx": "not-valid"})
        self.core.bus.emit(utt)

        # confirm all expected messages are sent
        expected_messages = [
            "recognizer_loop:utterance",
            f"{self.skill_id}.converse.ping",
            "skill.converse.pong",
            f"{self.skill_id}:HelloWorldIntent",
            "mycroft.skill.handler.start",
            "intent.service.skills.activate",
            "intent.service.skills.activated",
            f"{self.skill_id}.activate",
            "ovos.session.update_default",
            "enclosure.active_skill",
            "speak",
            "mycroft.skill.handler.complete",
            "ovos.session.update_default"
        ]
        wait_for_n_messages(len(expected_messages))

        self.assertEqual(len(expected_messages), len(messages))

        for idx, m in enumerate(messages):
            self.assertEqual(m.msg_type, expected_messages[idx])

        # verify that contexts are kept around
        for m in messages:
            self.assertEqual(m.context["session"]["session_id"], "default")
            self.assertEqual(m.context["xxx"], "not-valid")

        # verify ping/pong answer from hello world skill
        self.assertEqual(messages[1].msg_type, f"{self.skill_id}.converse.ping")
        self.assertEqual(messages[2].msg_type, "skill.converse.pong")
        self.assertEqual(messages[2].data["skill_id"], self.skill_id)
        self.assertEqual(messages[2].context["skill_id"], self.skill_id)
        self.assertFalse(messages[2].data["can_handle"])

        # verify intent triggers
        self.assertEqual(messages[3].msg_type, f"{self.skill_id}:HelloWorldIntent")
        self.assertEqual(messages[3].data["intent_type"], f"{self.skill_id}:HelloWorldIntent")
        # verify skill_id is now present in every message.context
        for m in messages[3:]:
            self.assertEqual(m.context["skill_id"], self.skill_id)

        self.assertEqual(messages[4].msg_type, "mycroft.skill.handler.start")
        # verify skill is activated
        self.assertEqual(messages[5].msg_type, "intent.service.skills.activate")
        self.assertEqual(messages[5].data["skill_id"], self.skill_id)
        self.assertEqual(messages[6].msg_type, "intent.service.skills.activated")
        self.assertEqual(messages[6].data["skill_id"], self.skill_id)
        self.assertEqual(messages[7].msg_type, f"{self.skill_id}.activate")
        self.assertEqual(messages[8].msg_type, "ovos.session.update_default")
        # verify intent code execution
        self.assertEqual(messages[9].msg_type, "enclosure.active_skill")
        self.assertEqual(messages[9].data["skill_id"], self.skill_id)
        self.assertEqual(messages[10].msg_type, "speak")
        self.assertEqual(messages[10].data["lang"], "en-us")
        self.assertFalse(messages[10].data["expect_response"])
        self.assertEqual(messages[10].data["meta"]["dialog"], "hello.world")
        self.assertEqual(messages[10].data["meta"]["skill"], self.skill_id)
        # intent complete
        self.assertEqual(messages[11].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[11].data["name"], "HelloWorldSkill.handle_hello_world_intent")

        # verify default session is now updated
        self.assertEqual(messages[12].msg_type, "ovos.session.update_default")
        self.assertEqual(messages[12].data["session_data"]["session_id"], "default")

        # test deserialization of payload
        sess = Session.deserialize(messages[12].data["session_data"])
        self.assertEqual(sess.session_id, "default")

        # test that active skills list has been updated
        self.assertEqual(messages[12].data["session_data"]["active_skills"][0][0], self.skill_id)
        self.assertEqual(sess.active_skills[0][0], self.skill_id)
        self.assertNotEqual(sess.active_skills[0][1], now)

    def test_explicit_session(self):
        SessionManager.sessions = {}
        SessionManager.default_session = SessionManager.sessions["default"] = Session("default")
        SessionManager.default_session.lang = "en-us"
        SessionManager.default_session.pipeline = [
            "converse",
            "adapt_high"
        ]

        messages = []

        def new_msg(msg):
            nonlocal messages
            m = Message.deserialize(msg)
            if m.msg_type in ["ovos.skills.settings_changed"]:
                return  # skip these, only happen in 1st run
            messages.append(m)
            print(len(messages), msg)

        def wait_for_n_messages(n):
            nonlocal messages
            t = time.time()
            while len(messages) < n:
                sleep(0.1)
                if time.time() - t > 10:
                    raise RuntimeError("did not get the number of expected messages under 10 seconds")

        self.core.bus.on("message", new_msg)

        sess = Session("test-session",
                       pipeline=[
                           "converse",
                           "adapt_high"
                       ])
        now = time.time()
        sess.active_skills = [(self.skill_id, now)]
        utt = Message("recognizer_loop:utterance",
                      {"utterances": ["hello world"]},
                      {"session": sess.serialize(),  # explicit
                       "xxx": "not-valid"})
        self.core.bus.emit(utt)

        # confirm all expected messages are sent
        expected_messages = [
            "recognizer_loop:utterance",
            f"{self.skill_id}.converse.ping",
            "skill.converse.pong",
            f"{self.skill_id}:HelloWorldIntent",
            "mycroft.skill.handler.start",
            "intent.service.skills.activate",
            "intent.service.skills.activated",
            f"{self.skill_id}.activate",
            "enclosure.active_skill",
            "speak",
            "mycroft.skill.handler.complete"
        ]
        wait_for_n_messages(len(expected_messages))

        self.assertEqual(len(expected_messages), len(messages))

        for idx, m in enumerate(messages):
            self.assertEqual(m.msg_type, expected_messages[idx])

        # verify that contexts are kept around
        for m in messages:
            self.assertEqual(m.context["session"]["session_id"], sess.session_id)
            self.assertEqual(m.context["xxx"], "not-valid")

        # verify ping/pong answer from hello world skill
        self.assertEqual(messages[1].msg_type, f"{self.skill_id}.converse.ping")
        self.assertEqual(messages[2].msg_type, "skill.converse.pong")
        self.assertEqual(messages[2].data["skill_id"], self.skill_id)
        self.assertEqual(messages[2].context["skill_id"], self.skill_id)
        self.assertFalse(messages[2].data["can_handle"])

        # verify intent triggers
        self.assertEqual(messages[3].msg_type, f"{self.skill_id}:HelloWorldIntent")
        self.assertEqual(messages[3].data["intent_type"], f"{self.skill_id}:HelloWorldIntent")
        # verify skill_id is now present in every message.context
        for m in messages[3:]:
            self.assertEqual(m.context["skill_id"], self.skill_id)

        # verify intent execution
        self.assertEqual(messages[4].msg_type, "mycroft.skill.handler.start")
        self.assertEqual(messages[4].data["name"], "HelloWorldSkill.handle_hello_world_intent")
        # verify skill is activated
        self.assertEqual(messages[5].msg_type, "intent.service.skills.activate")
        self.assertEqual(messages[5].data["skill_id"], self.skill_id)
        self.assertEqual(messages[6].msg_type, "intent.service.skills.activated")
        self.assertEqual(messages[6].data["skill_id"], self.skill_id)
        self.assertEqual(messages[7].msg_type, f"{self.skill_id}.activate")

        self.assertEqual(messages[8].msg_type, "enclosure.active_skill")
        self.assertEqual(messages[8].data["skill_id"], self.skill_id)
        self.assertEqual(messages[9].msg_type, "speak")
        self.assertEqual(messages[9].data["lang"], "en-us")
        self.assertFalse(messages[9].data["expect_response"])
        self.assertEqual(messages[9].data["meta"]["dialog"], "hello.world")
        self.assertEqual(messages[9].data["meta"]["skill"], self.skill_id)
        self.assertEqual(messages[10].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[10].data["name"], "HelloWorldSkill.handle_hello_world_intent")

        # test that active skills list has been updated
        sess = Session.from_message(messages[-1])
        self.assertEqual(sess.active_skills[0][0], self.skill_id)
        self.assertNotEqual(sess.active_skills[0][1], now)
        # test that default session remains unchanged
        self.assertEqual(SessionManager.default_session.active_skills, [])
