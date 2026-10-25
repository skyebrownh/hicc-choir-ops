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
from roster.models import Member, StatusChange
from roster.tests import make_member

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

        self.assertRedirects(self.enter_code(sent_code()), "/", target_status_code=302)

        self.assertContains(self.client.get("/", follow=True), "leader@example.com")

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
        self.assertRedirects(self.enter_code(second), "/", target_status_code=302)

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
            self.assertRedirects(self.enter_code(code), "/", target_status_code=302)

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

    def html_part(self):
        """The HTML version of the most recent email."""
        (html, mimetype), = mail.outbox[-1].alternatives
        self.assertEqual(mimetype, "text/html")
        return html

    def test_ac1_the_email_has_an_html_version_with_the_code_expiry_and_ignore_line(self):
        self.request_code()

        html = self.html_part()
        self.assertIn(sent_code(), html)
        self.assertIn("Your sign-in code", html)
        self.assertIn("Hello,", html)
        self.assertIn("It works for 10 minutes.", html)
        self.assertIn("If you didn't ask for this, ignore this email.", html)

    def test_ac2_both_email_versions_state_the_code_lifetime_in_force(self):
        with mock.patch("accounts.codes.CODE_LIFETIME", timedelta(minutes=15)):
            self.request_code()

        self.assertIn("It works for 15 minutes.", mail.outbox[-1].body)
        self.assertIn("It works for 15 minutes.", self.html_part())

    def test_ac1_the_html_email_has_no_links_images_or_style_blocks(self):
        self.request_code()

        html = self.html_part().lower()
        for forbidden in ("<a ", "<img", "<style", "<link", "http"):
            self.assertNotIn(forbidden, html)

    def test_ac1_the_text_email_keeps_the_code_line_and_adds_the_ignore_line(self):
        self.request_code()

        message = mail.outbox[-1]
        self.assertEqual(message.subject, "Your HICC Choir Ops sign-in code")
        self.assertIn(f"Your sign-in code is {sent_code()}. It works for 10 minutes.", message.body)
        self.assertIn("If you didn't ask for this, ignore this email.", message.body)

    def test_ac1_a_send_failure_is_logged_without_secrets_and_clears_the_code(self):
        with mock.patch("accounts.codes.EmailMultiAlternatives.send", side_effect=urllib.error.URLError("down")):
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

    def test_ac4_the_front_door_sends_an_admin_to_the_week_ahead_page(self):
        self.client.force_login(self.admin)

        self.assertRedirects(self.client.get("/"), "/week/")
        self.assertContains(self.client.get("/week/"), "Week ahead")

    def test_ac4_the_front_door_sends_a_section_leader_to_the_attendance_page(self):
        self.client.force_login(self.leader)

        self.assertRedirects(self.client.get("/"), "/attendance/")
        self.assertContains(self.client.get("/attendance/"), "Attendance")

    def test_ac4_a_role_that_may_not_see_a_page_gets_not_found(self):
        self.client.force_login(self.leader)
        self.assertEqual(self.client.get("/week/").status_code, 404)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/attendance/").status_code, 404)

    def test_ac4_signing_out_ends_the_session(self):
        self.client.force_login(self.admin)

        response = self.client.post("/signout/")

        self.assertRedirects(response, "/signin/")
        self.assertRedirects(
            self.client.get("/week/"), "/signin/?next=/week/", fetch_redirect_response=False
        )

    def test_ac4_signing_out_by_a_plain_link_does_nothing(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get("/signout/").status_code, 405)

        self.assertEqual(self.client.get("/week/").status_code, 200)

    def test_ac4_signed_in_pages_show_a_sign_out_button_and_sign_in_pages_do_not(self):
        self.assertNotContains(self.client.get("/signin/"), "Sign out")

        self.client.force_login(self.admin)

        self.assertContains(self.client.get("/week/"), "Sign out")

    def test_ac4_a_public_page_typed_without_its_trailing_slash_still_reaches_it(self):
        # Django adds the missing slash for us, but only if the sign-in check lets the
        # request through to find that out.
        for path in ("/health", "/health/db", "/signin", "/signin/code"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertRedirects(
                    response, f"{path}/", status_code=301, fetch_redirect_response=False
                )

    def test_ac4_a_path_that_only_starts_like_a_public_one_is_still_private(self):
        for path in ("/healthz/", "/signinx/", "/healthz"):
            with self.subTest(path=path):
                self.assertRedirects(
                    self.client.get(path), f"/signin/?next={path}", fetch_redirect_response=False
                )

    def test_ac4_static_files_need_no_sign_in(self):
        # A file that doesn't exist gets "not found", which proves the sign-in check let
        # the request through instead of redirecting it.
        self.assertEqual(self.client.get("/static/no-such-file.css").status_code, 404)

    def test_ac4_a_private_page_typed_without_its_trailing_slash_goes_to_sign_in(self):
        self.assertRedirects(
            self.client.get("/signout"), "/signin/?next=/signout", fetch_redirect_response=False
        )

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

        # With an email in the session, which is how a visitor arrives, it shows the form.
        session = self.client.session
        session["signin_email"] = "leader@example.com"
        session.save()
        self.assertEqual(self.client.get("/signin/code/").status_code, 200)


class ResendBackendTests(SimpleTestCase):
    def message(self, html="<p>Body 123456</p>"):
        message = mail.EmailMultiAlternatives(
            "Subject", "Body 123456", "HICC <signin@mail.example.com>", ["a@example.com"]
        )
        if html:
            message.attach_alternative(html, "text/html")
        return message

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
                "html": "<p>Body 123456</p>",
            },
        )

    @override_settings(RESEND_API_KEY="test-key")
    def test_ac1_a_message_without_html_is_sent_without_an_html_field(self):
        with mock.patch("accounts.email.urllib.request.urlopen") as urlopen:
            resend.ResendEmailBackend().send_messages([self.message(html=None)])

        self.assertNotIn("html", json.loads(urlopen.call_args.args[0].data))

    @override_settings(RESEND_API_KEY="test-key")
    def test_ac1_a_plain_email_message_is_sent_as_text_only(self):
        plain = mail.EmailMessage("Subject", "Body 123456", "HICC <signin@mail.example.com>", ["a@example.com"])
        with mock.patch("accounts.email.urllib.request.urlopen") as urlopen:
            sent = resend.ResendEmailBackend().send_messages([plain])

        self.assertEqual(sent, 1)
        self.assertNotIn("html", json.loads(urlopen.call_args.args[0].data))

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


@FAST_HASHER
class RateLimitTests(TestCase):
    """AC-7: code requests are capped per email address and per IP address, per hour."""

    def setUp(self):
        Account.objects.create_user("leader@example.com", sections=["alto"])

    def request_code(self, email="leader@example.com", **extra):
        return self.client.post("/signin/", {"email": email}, **extra)

    def test_ac7_the_sixth_request_for_one_email_in_an_hour_is_refused(self):
        for _ in range(5):
            self.assertRedirects(self.request_code(), "/signin/code/")
        sent_before = len(mail.outbox)

        response = self.request_code()

        self.assertContains(response, "Too many requests. Please try again later.", status_code=429)
        self.assertEqual(len(mail.outbox), sent_before)
        self.assertEqual(SignInCode.objects.count(), 1)  # the 5th request's code only

    def test_ac7_spellings_of_one_email_share_one_limit(self):
        for email in ["leader@example.com", "Leader@Example.com", "LEADER@example.com", "leader@EXAMPLE.com", "Leader@example.com"]:
            self.assertRedirects(self.request_code(email), "/signin/code/")

        self.assertContains(self.request_code("LEADER@Example.com"), "Too many requests", status_code=429)

    def test_ac7_requests_for_unknown_emails_count_too(self):
        for _ in range(5):
            self.assertContains(self.request_code("nobody@example.com"), "no account for that email")

        response = self.request_code("nobody@example.com")

        self.assertContains(response, "Too many requests. Please try again later.", status_code=429)
        self.assertEqual(len(mail.outbox), 0)

    def test_ac7_unknown_email_requests_count_toward_the_ip_limit(self):
        for number in range(20):
            self.request_code(f"guess{number}@example.com")

        self.assertContains(self.request_code("another@example.com"), "Too many requests", status_code=429)

    def test_ac7_one_ip_can_make_20_requests_across_emails_and_the_21st_is_refused(self):
        for number in range(20):
            self.assertContains(self.request_code(f"guess{number}@example.com"), "no account for that email")

        response = self.request_code("guess20@example.com")

        self.assertContains(response, "Too many requests. Please try again later.", status_code=429)

    def test_ac7_an_ip_that_used_up_its_20_does_not_hold_back_another_ip(self):
        for number in range(20):
            self.request_code(f"guess{number}@example.com", REMOTE_ADDR="10.0.0.1")
        self.assertContains(self.request_code("guess20@example.com", REMOTE_ADDR="10.0.0.1"), "Too many requests", status_code=429)

        # A different address has its own count of 20.
        self.assertContains(self.request_code("guess20@example.com", REMOTE_ADDR="10.0.0.2"), "no account for that email")

    def test_ac7_the_ip_limit_also_stops_a_real_account(self):
        for number in range(20):
            self.request_code(f"guess{number}@example.com")

        response = self.request_code("leader@example.com")

        self.assertContains(response, "Too many requests", status_code=429)
        self.assertEqual(len(mail.outbox), 0)

    def test_ac7_different_ips_have_separate_limits(self):
        for _ in range(5):
            self.request_code("nobody@example.com", REMOTE_ADDR="10.0.0.1")

        self.assertContains(self.request_code("nobody@example.com", REMOTE_ADDR="10.0.0.1"), "Too many requests", status_code=429)
        # Another IP asking for the same email is held back by the email limit, not the IP's.
        self.assertContains(self.request_code("nobody@example.com", REMOTE_ADDR="10.0.0.2"), "Too many requests", status_code=429)
        # ...but a different email from that other IP is fine.
        self.assertContains(self.request_code("other@example.com", REMOTE_ADDR="10.0.0.2"), "no account for that email")

    def test_ac7_different_emails_have_separate_limits(self):
        Account.objects.create_user("second@example.com", sections=["bass"])
        for _ in range(5):
            self.request_code("leader@example.com")

        self.assertRedirects(self.request_code("second@example.com"), "/signin/code/")

    def test_ac7_requests_work_again_once_an_hour_has_passed(self):
        for _ in range(5):
            self.request_code()
        self.assertContains(self.request_code(), "Too many requests", status_code=429)
        later = timezone.now() + timedelta(hours=1, seconds=1)

        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertRedirects(self.request_code(), "/signin/code/")

    def test_ac7_the_limit_still_holds_just_inside_the_hour(self):
        for _ in range(5):
            self.request_code()
        later = timezone.now() + timedelta(minutes=59)

        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertContains(self.request_code(), "Too many requests", status_code=429)

    def test_ac7_refused_requests_do_not_count_so_the_wait_ends_with_the_oldest_allowed_one(self):
        start = timezone.now()
        for _ in range(5):
            self.request_code()  # all five at `start`
        # Keep trying while refused: if these counted, they would extend the wait.
        with mock.patch("django.utils.timezone.now", return_value=start + timedelta(minutes=50)):
            for _ in range(10):
                self.assertContains(self.request_code(), "Too many requests", status_code=429)

        with mock.patch("django.utils.timezone.now", return_value=start + timedelta(hours=1, seconds=1)):
            self.assertRedirects(self.request_code(), "/signin/code/")

    @override_settings(NUM_PROXIES=0)
    def test_ac7_with_no_proxy_the_ip_is_the_connections_and_a_forged_forwarded_header_is_ignored(self):
        for number in range(20):
            # Each request claims a different origin; with no proxy these claims mean nothing.
            self.request_code(f"guess{number}@example.com", HTTP_X_FORWARDED_FOR=f"9.9.9.{number}")

        response = self.request_code("guess20@example.com", HTTP_X_FORWARDED_FOR="9.9.9.99")

        self.assertContains(response, "Too many requests", status_code=429)

    @override_settings(NUM_PROXIES=1)
    def test_ac7_with_one_proxy_the_ip_is_the_last_forwarded_entry(self):
        for number in range(20):
            self.request_code(f"guess{number}@example.com", REMOTE_ADDR="10.1.1.1", HTTP_X_FORWARDED_FOR="203.0.113.7")

        same = self.request_code("guess20@example.com", REMOTE_ADDR="10.1.1.2", HTTP_X_FORWARDED_FOR="203.0.113.7")
        other = self.request_code("guess20@example.com", REMOTE_ADDR="10.1.1.1", HTTP_X_FORWARDED_FOR="203.0.113.8")

        self.assertContains(same, "Too many requests", status_code=429)
        self.assertContains(other, "no account for that email")

    @override_settings(NUM_PROXIES=1)
    def test_ac7_with_one_proxy_a_forged_first_entry_does_not_dodge_the_limit(self):
        for number in range(20):
            # The client invents a new first entry each time; the proxy appended the real one last.
            self.request_code(f"guess{number}@example.com", HTTP_X_FORWARDED_FOR=f"1.2.3.{number}, 203.0.113.7")

        response = self.request_code("guess20@example.com", HTTP_X_FORWARDED_FOR="1.2.3.99, 203.0.113.7")

        self.assertContains(response, "Too many requests", status_code=429)


class AccountPagesTests(TestCase):
    """AC-5, AC-6: admins manage accounts on our own pages. Signed in as a role, through the test client."""

    def setUp(self):
        self.admin = Account.objects.create_superuser("admin@example.com")
        self.client.force_login(self.admin)

    def test_ac5_the_list_groups_admins_then_leaders_and_sorts_leaders_by_section_then_name(self):
        for name, sections in [("Zed Young", ["alto"]), ("Amy Walker", ["alto", "tenor"]), ("Sophie Reed", ["soprano"]), ("Tim Hayes", ["bass", "tenor"])]:
            member = make_member(name, sections[0])
            Account.objects.create_user(f"{name.split()[0].lower()}@example.com", sections=sections, member=member)

        response = self.client.get("/accounts/")

        self.assertEqual(
            [(label, [a.display_name for a in accounts]) for label, accounts in response.context["groups"]],
            [
                ("Admins", ["admin@example.com"]),
                ("Section leaders", ["Sophie Reed", "Amy Walker", "Zed Young", "Tim Hayes"]),
            ],
        )
        # The headings say the role, so rows carry no role badge.
        self.assertNotContains(response, ">Section leader<")

    def add(self, **fields):
        return self.client.post("/accounts/new/", fields)

    def test_ac5_admin_gives_a_member_an_account_as_a_leader_with_one_section(self):
        member = make_member("Sophie Reed", "soprano")

        response = self.add(email="sophie@example.com", role="section_leader", member=member.pk, sections=["soprano"])

        self.assertRedirects(response, "/accounts/")
        account = Account.objects.get(email="sophie@example.com")
        self.assertEqual((account.role, account.sections, account.member), (Role.SECTION_LEADER, ["soprano"], member))

    def test_ac5_a_leader_can_cover_several_sections(self):
        member = make_member("Tom Fisher", "tenor")

        self.add(email="tom@example.com", role="section_leader", member=member.pk, sections=["tenor", "bass"])

        self.assertCountEqual(Account.objects.get(email="tom@example.com").sections, ["tenor", "bass"])

    def test_ac5_an_admin_account_ignores_submitted_sections(self):
        member = make_member("Amy Walker", "alto")

        self.add(email="amy@example.com", role="admin", member=member.pk, sections=["alto"])

        account = Account.objects.get(email="amy@example.com")
        self.assertEqual((account.role, account.sections), (Role.ADMIN, []))

    def test_ac5_a_leader_with_no_section_is_rejected(self):
        member = make_member("Sophie Reed", "soprano")

        response = self.add(email="sophie@example.com", role="section_leader", member=member.pk)

        self.assertContains(response, "Pick at least one section")
        self.assertFalse(Account.objects.filter(email="sophie@example.com").exists())

    def test_ac5_a_leader_with_no_member_is_rejected(self):
        response = self.add(email="sophie@example.com", role="section_leader", sections=["soprano"])

        self.assertContains(response, "A section leader has to be a choir member")
        self.assertFalse(Account.objects.filter(email="sophie@example.com").exists())

    def test_ac6_an_admin_account_can_have_no_member_and_makes_no_member_record(self):
        response = self.add(email="director@example.com", role="admin")

        self.assertRedirects(response, "/accounts/")
        self.assertIsNone(Account.objects.get(email="director@example.com").member)
        self.assertEqual(Member.objects.count(), 0)

    def test_ac5_a_duplicate_email_in_any_letter_case_is_rejected(self):
        Account.objects.create_user("sophie@example.com", role=Role.ADMIN)

        response = self.add(email="Sophie@Example.com", role="admin")

        self.assertContains(response, "already has an account")
        self.assertEqual(Account.objects.count(), 2)

    def test_ac5_a_member_with_an_account_cannot_be_given_another(self):
        member = make_member("Sophie Reed", "soprano")
        Account.objects.create_user("sophie@example.com", sections=["soprano"], member=member)

        response = self.add(email="other@example.com", role="admin", member=member.pk)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Account.objects.filter(email="other@example.com").exists())

    def make_leader(self, name="Sophie Reed", section="soprano", sections=None):
        member = make_member(name, section)
        return Account.objects.create_user(
            f"{name.split()[0].lower()}@example.com", sections=sections or [section], member=member
        )

    def edit(self, account, **fields):
        return self.client.post(f"/accounts/{account.pk}/edit/", fields)

    def test_ac5_an_admin_changes_a_leaders_sections_and_it_applies_on_the_next_request(self):
        leader = self.make_leader()

        response = self.edit(leader, role="section_leader", member=leader.member_id, sections=["alto", "tenor"])

        self.assertRedirects(response, "/accounts/")
        self.client.force_login(Account.objects.get(pk=leader.pk))
        self.assertEqual(self.client.get("/members/").status_code, 200)
        self.assertCountEqual(Account.objects.get(pk=leader.pk).sections, ["alto", "tenor"])

    def test_ac5_changing_a_leader_to_admin_keeps_their_stored_sections_and_hides_the_boxes(self):
        leader = self.make_leader(sections=["soprano", "alto"])

        self.edit(leader, role="admin", member=leader.member_id, sections=["bass"])

        leader.refresh_from_db()
        self.assertEqual((leader.role, leader.sections), (Role.ADMIN, ["soprano", "alto"]))
        page = self.client.get(f"/accounts/{leader.pk}/edit/")
        self.assertContains(page, "Admins see all sections")
        self.assertContains(page, 'id="section-boxes" hidden')
        # The admin kept Soprano and Alto, yet the list shows no section badge for them.
        listing = self.client.get("/accounts/").content.decode()
        self.assertNotIn(">Soprano<", listing)
        self.assertNotIn(">Alto<", listing)

    def test_ac5_changing_an_admin_back_to_leader_needs_a_section_and_shows_the_stored_ones(self):
        leader = self.make_leader(sections=["soprano"])
        self.edit(leader, role="admin", member=leader.member_id)

        page = self.client.get(f"/accounts/{leader.pk}/edit/")
        self.assertRegex(page.content.decode(), r'value="soprano"[^>]*\bchecked')
        response = self.edit(leader, role="section_leader", member=leader.member_id)

        self.assertContains(response, "Pick at least one section")
        leader.refresh_from_db()
        self.assertEqual(leader.role, Role.ADMIN)

    def test_ac5_the_email_cannot_be_changed_on_the_edit_page(self):
        leader = self.make_leader()

        page = self.client.get(f"/accounts/{leader.pk}/edit/")
        self.edit(leader, email="new@example.com", role="section_leader", member=leader.member_id, sections=["soprano"])

        self.assertContains(page, "To change the email, remove this account and add it again.")
        leader.refresh_from_db()
        self.assertEqual(leader.email, "sophie@example.com")

    def test_ac5_an_admin_cannot_demote_their_own_account(self):
        member = make_member("Amy Walker", "alto")
        self.admin.member = member
        self.admin.save()

        response = self.edit(self.admin, role="section_leader", member=member.pk, sections=["alto"])

        self.assertContains(response, "take away your own admin access")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_ac5_removing_an_account_needs_the_confirm_page_to_be_submitted(self):
        leader = self.make_leader()

        page = self.client.get(f"/accounts/{leader.pk}/remove/")

        self.assertContains(page, "Remove the account for Sophie Reed?")
        self.assertTrue(Account.objects.filter(pk=leader.pk).exists())

    def test_ac5_an_admin_removes_an_account_and_that_person_can_no_longer_sign_in(self):
        leader = self.make_leader()

        response = self.client.post(f"/accounts/{leader.pk}/remove/")

        self.assertRedirects(response, "/accounts/")
        self.assertFalse(Account.objects.filter(pk=leader.pk).exists())
        self.assertEqual(Member.objects.filter(name="Sophie Reed").count(), 1)
        self.client.logout()
        self.assertContains(self.client.post("/signin/", {"email": "sophie@example.com"}), "no account for that email")

    def test_ac5_an_admin_cannot_remove_their_own_account(self):
        response = self.client.post(f"/accounts/{self.admin.pk}/remove/")

        self.assertContains(response, "own account")
        self.assertTrue(Account.objects.filter(pk=self.admin.pk).exists())

    def test_ac5_a_banner_confirms_an_account_was_added_changed_and_removed(self):
        member = make_member("Sophie Reed", "soprano")
        added = self.client.post(
            "/accounts/new/",
            {"email": "sophie@example.com", "role": "section_leader", "member": member.pk, "sections": ["soprano"]},
            follow=True,
        )
        account = Account.objects.get(email="sophie@example.com")
        changed = self.client.post(
            f"/accounts/{account.pk}/edit/",
            {"role": "section_leader", "member": member.pk, "sections": ["alto"]},
            follow=True,
        )
        removed = self.client.post(f"/accounts/{account.pk}/remove/", follow=True)

        self.assertContains(added, "Account added")
        self.assertContains(changed, "Account changed")
        self.assertContains(removed, "Account removed")

    def test_ac5_the_accounts_nav_link_shows_for_admins_and_not_for_leaders(self):
        self.assertContains(self.client.get("/week/"), 'href="/accounts/"')

        self.client.force_login(self.make_leader())

        self.assertNotContains(self.client.get("/attendance/"), 'href="/accounts/"')

    def test_ac5_the_accounts_link_comes_before_the_members_link(self):
        page = self.client.get("/week/").content.decode()

        self.assertLess(page.index('href="/accounts/"'), page.index('href="/members/"'))

    def test_ac8_every_page_says_who_is_signed_in_by_member_name_or_email(self):
        self.assertContains(self.client.get("/week/"), "Signed in as admin@example.com")

        leader = self.make_leader()
        self.client.force_login(leader)

        self.assertContains(self.client.get("/attendance/"), "Signed in as Sophie Reed")

    def test_ac8_the_signed_in_line_is_not_shown_to_visitors(self):
        self.client.logout()

        self.assertNotContains(self.client.get("/signin/"), "Signed in as")

    def test_ac8_the_list_marks_your_own_account_as_you(self):
        self.make_leader()

        listing = self.client.get("/accounts/").content.decode()

        # Only the admin's own row: the leader's row has no marker.
        self.assertEqual(listing.count(">You<"), 1)
        self.assertLess(listing.index(">You<"), listing.index("Sophie Reed"))

    def assert_in_order(self, page, *pieces):
        positions = [page.index(piece) for piece in pieces]
        self.assertEqual(positions, sorted(positions), pieces)

    def test_ac5_the_member_dropdown_groups_members_by_section_in_choir_order(self):
        make_member("Ben Carter", "bass")
        make_member("Amy Walker", "alto")
        make_member("Sophie Reed", "soprano")

        page = self.client.get("/accounts/new/").content.decode()

        self.assert_in_order(
            page, '<optgroup label="Soprano">', "Sophie Reed", '<optgroup label="Alto">', "Amy Walker",
            '<optgroup label="Bass">', "Ben Carter",
        )

    def test_ac5_a_member_with_no_section_or_status_yet_is_listed_under_no_section(self):
        Member.objects.create(name="Nina New")

        page = self.client.get("/accounts/new/").content.decode()

        self.assert_in_order(page, '<optgroup label="No section">', "Nina New")

    def test_ac5_members_who_already_have_an_account_are_shown_greyed_out(self):
        taken = make_member("Sophie Reed", "soprano")
        free = make_member("Amy Walker", "alto")
        Account.objects.create_user("sophie@example.com", sections=["soprano"], member=taken)

        page = self.client.get("/accounts/new/").content.decode()

        self.assertRegex(page, rf'<option value="{taken.pk}"[^>]*\bdisabled[^>]*>\s*Sophie Reed \(has an account\)')
        self.assertNotRegex(page, rf'<option value="{free.pk}"[^>]*\bdisabled')

    def test_ac5_inactive_members_are_left_out_of_the_dropdown_and_the_page_says_so(self):
        gone = make_member("Ian Stone", "tenor")
        StatusChange.objects.create(member=gone, status="inactive", effective_on=timezone.localdate())
        make_member("Tom Fisher", "tenor")

        response = self.client.get("/accounts/new/")

        self.assertNotContains(response, "Ian Stone")
        self.assertContains(response, "Tom Fisher")
        self.assertContains(response, "Inactive members aren't listed.")

    def test_ac5_an_inactive_member_cannot_be_given_an_account(self):
        gone = make_member("Ian Stone", "tenor")
        StatusChange.objects.create(member=gone, status="inactive", effective_on=timezone.localdate())

        response = self.add(email="ian@example.com", role="section_leader", member=gone.pk, sections=["tenor"])

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Account.objects.filter(email="ian@example.com").exists())

    def test_ac5_editing_an_account_keeps_its_own_member_in_the_dropdown_even_if_inactive(self):
        leader = self.make_leader("Ian Stone", "tenor")
        StatusChange.objects.create(member=leader.member, status="inactive", effective_on=timezone.localdate())

        page = self.client.get(f"/accounts/{leader.pk}/edit/").content.decode()

        self.assertRegex(page, rf'<option value="{leader.member_id}" selected>')

    def test_ac8_your_own_member_is_marked_you_in_the_dropdown(self):
        me = make_member("Amy Walker", "alto")
        self.admin.member = me
        self.admin.save()
        make_member("Sophie Reed", "soprano")

        page = self.client.get("/accounts/new/").content.decode()

        self.assertIn("Amy Walker (you, has an account)", page)
        self.assertNotIn("Sophie Reed (", page)


class AccountPagePermissionTests(TestCase):
    """AC-5: a section leader asking for an account page gets "not found"; a visitor is sent to sign in."""

    def setUp(self):
        self.target = Account.objects.create_user("target@example.com", role=Role.ADMIN)
        self.paths = ["/accounts/", "/accounts/new/", f"/accounts/{self.target.pk}/edit/", f"/accounts/{self.target.pk}/remove/"]

    def test_ac5_a_section_leader_gets_not_found_on_every_account_page_for_get_and_post(self):
        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))

        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.client.post(path, {"email": "x@example.com", "role": "admin"}).status_code, 404)
        self.assertEqual(Account.objects.count(), 2)

    def test_ac5_a_visitor_who_is_not_signed_in_is_sent_to_sign_in(self):
        for path in self.paths:
            with self.subTest(path=path):
                self.assertRedirects(self.client.get(path), f"/signin/?next={path}")

    def test_ac5_an_admin_can_open_every_account_page(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
