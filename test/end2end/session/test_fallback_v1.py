import time
from time import sleep
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager, Session
from ..minicroft import get_minicroft


class TestFallback(TestCase):

    def setUp(self):
        self.skill_id = "skill-ovos-fallback-unknownv1.openvoiceos"
        self.core = get_minicroft(self.skill_id)

    def tearDown(self) -> None:
        self.core.stop()

    def test_fallback_v1(self):
        SessionManager.sessions = {}
        SessionManager.default_session = SessionManager.sessions["default"] = Session("default")
        SessionManager.default_session.lang = "en-us"
        SessionManager.default_session.pipeline = [
                           "converse",
                           "fallback_high",
                           "fallback_medium",
                           "fallback_low"
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
                      {"utterances": ["invalid"]},
                      {"session": SessionManager.default_session.serialize(),  # explicit default sess
                       "x": "xx"})
        self.core.bus.emit(utt)

        # confirm all expected messages are sent
        expected_messages = [
            "recognizer_loop:utterance",
            # FallbackV1 - high prio
            "mycroft.skills.fallback",
            "mycroft.skill.handler.start",
            "mycroft.skill.handler.complete",
            "mycroft.skills.fallback.response",
            # FallbackV1 - medium prio
            "mycroft.skills.fallback",
            "mycroft.skill.handler.start",
            "mycroft.skill.handler.complete",
            "mycroft.skills.fallback.response",
            # FallbackV1 - low prio -> skill selected
            "mycroft.skills.fallback",
            "mycroft.skill.handler.start",
            "enclosure.active_skill",
            "speak",
            # activation from skill, because fallback consumed utterance
            "intent.service.skills.activate",
            "intent.service.skills.activated",
            f"{self.skill_id}.activate",
            "ovos.session.update_default",
            # report handling
            "mycroft.skill.handler.complete",
            "mycroft.skills.fallback.response",
            # update default sess
            "ovos.session.update_default"
        ]
        wait_for_n_messages(len(expected_messages))

        self.assertEqual(len(expected_messages), len(messages))

        for idx, m in enumerate(messages):
            self.assertEqual(m.msg_type, expected_messages[idx])

        # verify that contexts are kept around
        for m in messages:
            self.assertEqual(m.context["session"]["session_id"], "default")
            self.assertEqual(m.context["x"], "xx")
        # verify active skills is empty until "intent.service.skills.activated"
        for m in messages[:14]:
            self.assertEqual(m.context["session"]["session_id"], "default")
            self.assertEqual(m.context["session"]["active_skills"], [])

        # high prio fallback
        self.assertEqual(messages[1].msg_type, "mycroft.skills.fallback")
        self.assertEqual(messages[1].data["fallback_range"], [0, 5])
        self.assertEqual(messages[2].msg_type, "mycroft.skill.handler.start")
        self.assertEqual(messages[2].data["handler"], "fallback")
        self.assertEqual(messages[3].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[3].data["handler"], "fallback")
        self.assertEqual(messages[4].msg_type, "mycroft.skills.fallback.response")
        self.assertFalse(messages[4].data["handled"])

        # medium prio fallback
        self.assertEqual(messages[5].msg_type, "mycroft.skills.fallback")
        self.assertEqual(messages[5].data["fallback_range"], [5, 90])
        self.assertEqual(messages[6].msg_type, "mycroft.skill.handler.start")
        self.assertEqual(messages[6].data["handler"], "fallback")
        self.assertEqual(messages[7].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[7].data["handler"], "fallback")
        self.assertEqual(messages[8].msg_type, "mycroft.skills.fallback.response")
        self.assertFalse(messages[8].data["handled"])

        # low prio fallback
        self.assertEqual(messages[9].msg_type, "mycroft.skills.fallback")
        self.assertEqual(messages[9].data["fallback_range"], [90, 101])
        self.assertEqual(messages[10].msg_type, "mycroft.skill.handler.start")
        self.assertEqual(messages[10].data["handler"], "fallback")

        # skill execution
        self.assertEqual(messages[11].msg_type, "enclosure.active_skill")
        self.assertEqual(messages[11].data["skill_id"], self.skill_id)
        self.assertEqual(messages[12].msg_type, "speak")
        self.assertEqual(messages[12].data["meta"]["dialog"], "unknown")
        self.assertEqual(messages[12].data["meta"]["skill"], self.skill_id)

        # skill making itself active
        self.assertEqual(messages[13].msg_type, "intent.service.skills.activate")
        self.assertEqual(messages[13].data["skill_id"], self.skill_id)
        self.assertEqual(messages[14].msg_type, "intent.service.skills.activated")
        self.assertEqual(messages[14].data["skill_id"], self.skill_id)
        self.assertEqual(messages[15].msg_type, f"{self.skill_id}.activate")
        self.assertEqual(messages[16].msg_type, 'ovos.session.update_default')

        # fallback execution response
        self.assertEqual(messages[17].msg_type, "mycroft.skill.handler.complete")
        self.assertEqual(messages[17].data["handler"], "fallback")
        self.assertEqual(messages[18].msg_type, "mycroft.skills.fallback.response")
        self.assertTrue(messages[18].data["handled"])

        # verify default session is now updated
        self.assertEqual(messages[19].msg_type, "ovos.session.update_default")
        self.assertEqual(messages[19].data["session_data"]["session_id"], "default")

        # test second message with no session resumes default active skills
        messages = []
        utt = Message("recognizer_loop:utterance",
                      {"utterances": ["invalid"]})
        self.core.bus.emit(utt)
        # converse ping/pong due being active
        expected_messages.extend([f"{self.skill_id}.converse.ping", "skill.converse.pong"])
        wait_for_n_messages(len(expected_messages))
        self.assertEqual(len(expected_messages), len(messages))

        # verify that contexts are kept around
        for m in messages[1:]:
            self.assertEqual(m.context["session"]["session_id"], "default")
            self.assertEqual(m.context["session"]["active_skills"][0][0], self.skill_id)
