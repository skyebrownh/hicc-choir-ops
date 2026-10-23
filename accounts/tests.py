"""Sign-in by emailed code. Everything goes through the test client, like a visitor would."""

import io
import json
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth.hashers import identify_hasher
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts import email as resend
from accounts.models import Account, Role, SignInCode

# Django's default hasher is deliberately slow; MD5 keeps every code check fast in tests.
FAST_HASHER = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def sent_code():
    """The 6-digit code from the most recent email."""
    return mail.outbox[-1].body.split("code is ")[1][:6]


@FAST_HASHER
class SignInTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create_user("leader@example.com", sections=["alto"])

    def request_code(self, email="leader@example.com"):
        return self.client.post("/signin/", {"email": email})

    def enter_code(self, code):
        return self.client.post("/signin/code/", {"code": code})

    def test_ac1_valid_email_then_valid_code_signs_the_person_in(self):
        self.assertRedirects(self.request_code(), "/signin/code/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["leader@example.com"])

        self.assertRedirects(self.enter_code(sent_code()), "/")

        self.assertContains(self.client.get("/"), "leader@example.com")

    def test_ac1_email_is_matched_ignoring_case(self):
        self.assertRedirects(self.request_code("Leader@Example.com"), "/signin/code/")

    def test_ac1_the_code_is_stored_hashed_never_as_digits(self):
        self.request_code()

        stored = SignInCode.objects.get().code

        self.assertNotEqual(stored, sent_code())
        self.assertEqual(identify_hasher(stored).algorithm, "md5")

    def test_ac1_a_new_request_replaces_the_earlier_code(self):
        self.request_code()
        first = sent_code()
        self.request_code()
        second = sent_code()

        self.assertEqual(SignInCode.objects.count(), 1)
        if first != second:  # one chance in a million they match
            self.assertContains(self.enter_code(first), "isn&#x27;t right")
        self.assertRedirects(self.enter_code(second), "/")

    def test_ac1_two_accounts_cannot_differ_only_by_email_case(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Account.objects.create_user("Leader@Example.com")

    def test_ac1_the_code_page_without_an_email_goes_back_to_the_start(self):
        self.assertRedirects(self.client.get("/signin/code/"), "/signin/")

    def test_ac1_home_needs_sign_in(self):
        self.assertRedirects(self.client.get("/"), "/signin/?next=/", fetch_redirect_response=False)

    def test_ac2_a_code_expires_after_10_minutes(self):
        self.request_code()
        code = sent_code()
        later = timezone.now() + timedelta(minutes=10, seconds=1)

        with mock.patch("accounts.codes.timezone.now", return_value=later):
            response = self.enter_code(code)

        self.assertContains(response, "That code has expired. Request a new one.")

    def test_ac2_a_code_still_works_just_inside_10_minutes(self):
        self.request_code()
        code = sent_code()
        later = timezone.now() + timedelta(minutes=9, seconds=59)

        with mock.patch("accounts.codes.timezone.now", return_value=later):
            self.assertRedirects(self.enter_code(code), "/")

    def test_ac2_a_code_works_once(self):
        self.request_code()
        code = sent_code()
        self.enter_code(code)
        self.client.logout()
        session = self.client.session
        session["signin_email"] = "leader@example.com"
        session.save()

        response = self.enter_code(code)

        self.assertContains(response, "Too many tries. Request a new code.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ac2_a_wrong_code_says_so(self):
        self.request_code()

        response = self.enter_code("000000" if sent_code() != "000000" else "111111")

        self.assertContains(response, "That code isn&#x27;t right. Try again.")

    def test_ac2_the_fifth_wrong_try_locks_the_code_even_for_the_right_one(self):
        self.request_code()
        right = sent_code()
        wrong = "000000" if right != "000000" else "111111"
        for _ in range(4):
            self.assertContains(self.enter_code(wrong), "isn&#x27;t right")

        self.assertContains(self.enter_code(wrong), "Too many tries. Request a new code.")
        self.assertContains(self.enter_code(right), "Too many tries. Request a new code.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ac3_an_unknown_email_says_so_sends_nothing_and_stores_nothing(self):
        response = self.request_code("nobody@example.com")

        self.assertContains(
            response, "There&#x27;s no account for that email. Check the spelling, or ask the director."
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(SignInCode.objects.count(), 0)
        self.assertNotIn("signin_email", self.client.session)

    def test_ac1_a_send_failure_is_logged_without_secrets_and_clears_the_code(self):
        with mock.patch("accounts.codes.send_mail", side_effect=urllib.error.URLError("down")):
            with self.assertLogs("accounts.views", level="ERROR") as logs:
                response = self.request_code()

        self.assertContains(response, "We couldn&#x27;t send your code right now. Please try again in a minute.")
        self.assertEqual(SignInCode.objects.count(), 0)
        self.assertNotIn("leader@example.com", "".join(logs.output))

    def test_ac5_groundwork_an_admin_can_open_the_admin_but_a_section_leader_cannot(self):
        admin = Account.objects.create_user("boss@example.com", role=Role.ADMIN)

        self.client.force_login(admin)
        self.assertEqual(self.client.get("/admin/accounts/account/").status_code, 200)

        self.client.force_login(self.account)
        self.assertEqual(self.client.get("/admin/accounts/account/").status_code, 302)

    def test_ac1_createsuperuser_asks_only_for_an_email_never_a_password(self):
        with mock.patch("builtins.input", return_value="asked@example.com"), mock.patch(
            "getpass.getpass", side_effect=AssertionError("asked for a password")
        ):
            call_command("createsuperuser", verbosity=0)

        asked = Account.objects.get(email="asked@example.com")
        self.assertEqual(asked.role, Role.ADMIN)
        self.assertFalse(asked.has_usable_password())

    def test_ac1_createsuperuser_makes_an_admin_with_no_usable_password(self):
        call_command(
            "createsuperuser", interactive=False, email="owner@example.com", verbosity=0
        )

        owner = Account.objects.get(email="owner@example.com")
        self.assertEqual(owner.role, Role.ADMIN)
        self.assertFalse(owner.has_usable_password())


class StaySignedInTests(TestCase):
    """AC-4: stay signed in, sign out, and each role's own home page."""

    def setUp(self):
        self.admin = Account.objects.create_user("boss@example.com", role=Role.ADMIN)
        self.leader = Account.objects.create_user("leader@example.com", sections=["alto"])

    @FAST_HASHER
    def test_ac4_a_signed_in_session_lasts_90_days(self):
        # Sign in for real: force_login sets its own cookie, so it can't show what we send.
        self.client.post("/signin/", {"email": "boss@example.com"})
        response = self.client.post("/signin/code/", {"code": sent_code()})

        self.assertEqual(int(response.cookies["sessionid"]["max-age"]), 90 * 24 * 60 * 60)


    def test_ac4_a_signed_out_visitor_is_sent_to_sign_in_from_any_page(self):
        for path in ("/", "/week/", "/no-such-page/", "/admin/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertRedirects(
                    response, f"/signin/?next={path}", fetch_redirect_response=False
                )

    def test_ac4_the_health_checks_and_sign_in_pages_need_no_sign_in(self):
        for path in ("/health/", "/health/db/", "/signin/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        # With no email in the session this page sends you back to the start itself. A
        # "?next=" on the redirect would mean the sign-in check stepped in instead.
        self.assertRedirects(self.client.get("/signin/code/"), "/signin/")


class ResendBackendTests(SimpleTestCase):
    def message(self):
        return mail.EmailMessage("Subject", "Body 123456", "HICC <signin@mail.example.com>", ["a@example.com"])

    @override_settings(RESEND_API_KEY="test-key")
    def test_ac1_it_posts_the_message_to_resend_with_the_right_headers_and_timeout(self):
        with mock.patch("accounts.email.urllib.request.urlopen") as urlopen:
            sent = resend.ResendEmailBackend().send_messages([self.message()])

        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertTrue(request.get_header("User-agent"))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)
        self.assertEqual(
            json.loads(request.data),
            {
                "from": "HICC <signin@mail.example.com>",
                "to": ["a@example.com"],
                "subject": "Subject",
                "text": "Body 123456",
            },
        )

    @override_settings(RESEND_API_KEY="test-key")
    def test_ac1_it_raises_when_resend_answers_with_an_error(self):
        error = urllib.error.HTTPError("https://api.resend.com/emails", 403, "Forbidden", {}, io.BytesIO())
        with mock.patch("accounts.email.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                resend.ResendEmailBackend().send_messages([self.message()])

    @override_settings(RESEND_API_KEY="")
    def test_ac1_it_raises_when_there_is_no_api_key(self):
        with mock.patch("accounts.email.urllib.request.urlopen") as urlopen:
            with self.assertRaises(RuntimeError):
                resend.ResendEmailBackend().send_messages([self.message()])

        urlopen.assert_not_called()


class EmailBackendChoiceTests(SimpleTestCase):
    """The backend is chosen when settings load, so load them again with a changed environment."""

    def backend_for(self, **env):
        import importlib
        import os

        from config import settings

        with mock.patch.dict(os.environ, env, clear=False):
            for name in ("DEBUG", "RESEND_API_KEY"):
                if name not in env:
                    os.environ.pop(name, None)
            return importlib.reload(settings).EMAIL_BACKEND

    def tearDown(self):
        import importlib

        from config import settings

        importlib.reload(settings)

    def test_ac1_debug_without_a_key_prints_codes_to_the_console(self):
        self.assertEqual(
            self.backend_for(DEBUG="true"), "django.core.mail.backends.console.EmailBackend"
        )

    def test_ac1_debug_with_a_key_uses_resend(self):
        self.assertEqual(
            self.backend_for(DEBUG="true", RESEND_API_KEY="k"), "accounts.email.ResendEmailBackend"
        )

    def test_ac1_production_without_a_key_still_uses_resend_so_sending_fails_loudly(self):
        self.assertEqual(self.backend_for(DEBUG="false"), "accounts.email.ResendEmailBackend")
