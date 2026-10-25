"""Tests for the deploy pipeline's one real page, the health check, and the static setup.

Everything goes through Django's test client, like a visitor or Railway would.
"""

import tempfile
from datetime import timedelta
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import OperationalError
from django.utils import timezone
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import Account, Role
from roster.models import Member, StatusChange
from config.env import allowed_hosts


class HealthCheckTests(TestCase):
    def test_health_returns_ok_without_login_or_database(self):
        # Railway's check only asks "is the process up", so it must not query the database.
        with self.assertNumQueries(0):
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_health_is_not_redirected_to_https(self):
        # Railway calls over plain HTTP; a redirect would make every deploy look unhealthy.
        with override_settings(SECURE_SSL_REDIRECT=True):
            health = self.client.get("/health/")
            other_page = self.client.get("/admin/login/")

        self.assertEqual(health.status_code, 200)
        # Control: the redirect really is on for other pages, so the exemption proves something.
        self.assertEqual(other_page.status_code, 301)

    def test_health_answers_the_railway_health_check_host(self):
        response = self.client.get("/health/", HTTP_HOST="healthcheck.railway.app")

        self.assertEqual(response.status_code, 200)

    def test_health_db_returns_ok_when_the_database_answers(self):
        response = self.client.get("/health/db/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_health_db_returns_503_when_the_database_does_not_answer(self):
        # Simulated: we can't make the real test database go away mid-test.
        with mock.patch("config.views.connection.cursor", side_effect=OperationalError):
            response = self.client.get("/health/db/")

        self.assertEqual(response.status_code, 503)


class AdminTests(TestCase):
    def test_admin_login_sends_people_to_the_code_sign_in(self):
        response = self.client.get("/admin/login/")

        self.assertRedirects(response, "/signin/")

    def test_ac1_admin_renders_with_unfold_styling_for_a_signed_in_admin(self):
        admin = Account.objects.create_superuser("admin@example.com")
        self.client.force_login(admin)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "unfold")


class StaticFilesTests(SimpleTestCase):
    def test_built_css_is_served_by_whitenoise(self):
        # In production `collectstatic` gathers the files and WhiteNoise serves them from
        # STATIC_ROOT; do the same here, into a throwaway folder.
        with tempfile.TemporaryDirectory() as static_root, override_settings(STATIC_ROOT=static_root):
            call_command("collectstatic", interactive=False, verbosity=0)
            response = self.client.get("/static/app.css")

            self.assertEqual(response.status_code, 200)
            self.assertIn("text/css", response["Content-Type"])


class AllowedHostsTests(SimpleTestCase):
    def test_local_hosts_are_allowed_only_in_debug(self):
        # Without these, `runserver` at 127.0.0.1 answers 400 once any host is configured.
        self.assertIn("127.0.0.1", allowed_hosts(debug=True, extra=["app.example.com"]))
        self.assertNotIn("127.0.0.1", allowed_hosts(debug=False, extra=["app.example.com"]))
        self.assertIn("app.example.com", allowed_hosts(debug=False, extra=["app.example.com"]))


@override_settings(DEBUG=True)
class SeedTests(TestCase):
    def test_seed_basic_creates_fake_members_in_every_section_and_two_leaders(self):
        call_command("seed", "basic", verbosity=0)

        self.assertGreaterEqual(Member.objects.count(), 12)
        members = list(Member.objects.all())
        self.assertEqual({m.current_section for m in members}, {"soprano", "alto", "tenor", "bass"})
        self.assertIn(True, {m.current_praise_team for m in members})
        self.assertIn(False, {m.current_praise_team for m in members})
        leaders = Account.objects.filter(role=Role.SECTION_LEADER)
        self.assertEqual(sorted(leader.sections for leader in leaders), [["alto"], ["tenor", "bass"]])

    def test_seed_basic_links_each_leader_to_a_member_in_their_sections_and_adds_an_admin_with_no_member(self):
        call_command("seed", "basic", verbosity=0)
        call_command("seed", "basic", verbosity=0)  # admins are kept, so a second seed must not trip over the first

        for leader in Account.objects.filter(role=Role.SECTION_LEADER):
            self.assertIn(leader.member.current_section, leader.sections)
        self.assertEqual(Account.objects.filter(role=Role.ADMIN, member__isnull=True).count(), 1)

    def test_seed_basic_gives_every_member_a_status_and_one_a_break_history(self):
        call_command("seed", "basic", verbosity=0)

        others = Member.objects.exclude(name__in=["Beth Rowe", "Ian Stone"])
        self.assertTrue(all(member.current_status == "active" for member in others))
        returning = Member.objects.get(name="Amy Walker")
        self.assertEqual(
            [change.status for change in returning.status_history()], ["active", "on_break", "active"]
        )

    def test_seed_basic_has_one_member_on_break_and_one_inactive_for_trying_the_roster_filters(self):
        call_command("seed", "basic", verbosity=0)

        self.assertEqual(Member.objects.get(name="Beth Rowe").current_status, "on_break")
        self.assertEqual(Member.objects.get(name="Ian Stone").current_status, "inactive")

    def test_seed_basic_dates_statuses_from_today_not_a_year_ago(self):
        call_command("seed", "basic", verbosity=0)

        today = timezone.localdate()
        others = Member.objects.exclude(name="Amy Walker")
        for member in others:
            self.assertEqual([c.effective_on for c in member.status_history()], [today], member.name)
        # Amy's history is recent (this season), and never in the future.
        amy_dates = [c.effective_on for c in Member.objects.get(name="Amy Walker").status_history()]
        self.assertEqual(amy_dates[0], today)
        self.assertTrue(all(today - timedelta(days=120) <= d <= today for d in amy_dates))

    def test_seed_basic_gives_a_member_who_moved_section_and_one_who_joined_the_praise_team(self):
        call_command("seed", "basic", verbosity=0)

        today = timezone.localdate()
        moved = Member.objects.get(name="Tim Hayes")
        self.assertEqual([c.section for c in moved.section_history()], ["tenor", "alto"])
        self.assertEqual(moved.section_on(today - timedelta(days=60)), "alto")
        joined = Member.objects.get(name="Amy Walker")
        self.assertEqual([c.praise_team for c in joined.praise_team_history()], [True, False])
        # Everyone else has one dated row of each, from today.
        for member in Member.objects.exclude(name__in=["Tim Hayes", "Amy Walker"]):
            self.assertEqual(member.section_changes.count(), 1, member.name)
            self.assertEqual(member.praise_team_changes.count(), 1, member.name)

    def test_seed_keeps_admin_accounts_and_removes_other_accounts_and_members(self):
        Account.objects.create_superuser("admin@example.com")
        Account.objects.create_user("old-leader@example.com", sections=["alto"])
        Member.objects.create(name="Old Member")

        call_command("seed", "basic", verbosity=0)

        self.assertTrue(Account.objects.filter(email="admin@example.com", role=Role.ADMIN).exists())
        self.assertFalse(Account.objects.filter(email="old-leader@example.com").exists())
        self.assertFalse(Member.objects.filter(name="Old Member").exists())

    def test_seed_twice_gives_the_same_result(self):
        call_command("seed", "basic", verbosity=0)
        first = (Member.objects.count(), Account.objects.count())

        call_command("seed", "basic", verbosity=0)

        self.assertEqual((Member.objects.count(), Account.objects.count()), first)

    def test_seed_refuses_an_unknown_scenario_and_lists_the_known_ones(self):
        Member.objects.create(name="Keep Me")

        with self.assertRaisesMessage(CommandError, "basic"):
            call_command("seed", "nope", verbosity=0)

        self.assertTrue(Member.objects.filter(name="Keep Me").exists())

    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_with_debug_off(self):
        # Wiping data is only safe on a developer's machine, never in production.
        Member.objects.create(name="Keep Me")

        with self.assertRaisesMessage(CommandError, "DEBUG"):
            call_command("seed", "basic", verbosity=0)

        self.assertTrue(Member.objects.filter(name="Keep Me").exists())
