"""Members: adding, editing and viewing. Everything goes through the test client, signed in as a role."""

import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import Account
from roster.models import Event, Member, PraiseTeamChange, SectionChange, StatusChange


def today():
    # Same clock the app uses (US Eastern), so tests agree with it near midnight UTC.
    return timezone.localdate()


def make_member(name, section, praise_team=False, since=date(2026, 1, 1), **fields):
    """A member whose section and Praise Team flag started on `since` (RO-6), like the app's Add form."""
    member = Member.objects.create(name=name, **fields)
    SectionChange.objects.create(member=member, section=section, effective_on=since)
    PraiseTeamChange.objects.create(member=member, praise_team=praise_team, effective_on=since)
    return member


class MemberTests(TestCase):
    def setUp(self):
        self.admin = Account.objects.create_superuser("admin@example.com")
        self.client.force_login(self.admin)

    def test_ro1_admin_adds_a_member_with_every_field(self):
        response = self.client.post(
            "/members/new/",
            {
                "name": "Grace Hopper",
                "phone": "555-0100",
                "email": "grace@example.com",
                "initial_section": "alto",
                "initial_praise_team": "on",
                "notes": "Sings 2nd service only",
            },
        )

        member = Member.objects.get()
        self.assertRedirects(response, f"/members/{member.pk}/")
        detail = self.client.get(f"/members/{member.pk}/")
        for shown in ["Grace Hopper", "555-0100", "grace@example.com", "Alto", "Sings 2nd service only"]:
            self.assertContains(detail, shown)
        self.assertTrue(member.current_praise_team)
        self.assertEqual(member.current_section, "alto")

    def test_ro1_the_praise_team_label_shows_only_for_members_on_it(self):
        on = make_member(name="Ann On", section="alto", praise_team=True)
        off = make_member(name="Bob Off", section="bass", praise_team=False)

        for url, shown in [(f"/members/{on.pk}/", True), (f"/members/{off.pk}/", False)]:
            response = self.client.get(url)
            self.assertEqual(shown, "Praise Team</span>" in response.content.decode(), url)
        # The list marks the same member rows.
        self.assertContains(self.client.get("/members/"), "Praise Team</span>", count=1)

    def test_ro1_phone_and_email_can_be_blank(self):
        response = self.client.post("/members/new/", {"name": "Ada", "initial_section": "bass"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Member.objects.get().phone, "")

    def test_ro1_a_missing_name_is_rejected(self):
        response = self.client.post("/members/new/", {"name": "", "initial_section": "bass"})

        self.assertContains(response, "This field is required")
        self.assertFalse(Member.objects.exists())

    def test_ro1_a_malformed_email_is_rejected(self):
        response = self.client.post("/members/new/", {"name": "Ada", "initial_section": "bass", "email": "not-an-email"})

        self.assertContains(response, "Enter a valid email address")
        self.assertFalse(Member.objects.exists())

    def test_ro3_admin_edits_a_member_and_the_changes_show(self):
        member = make_member(name="Ada", section="bass")

        response = self.client.post(
            f"/members/{member.pk}/edit/", {"name": "Ada Lovelace", "phone": "555-0111", "notes": "Moved up"}
        )

        self.assertRedirects(response, f"/members/{member.pk}/")
        detail = self.client.get(f"/members/{member.pk}/")
        for shown in ["Ada Lovelace", "Bass", "555-0111", "Moved up"]:
            self.assertContains(detail, shown)

    def test_ro3_the_edit_page_starts_filled_in(self):
        member = make_member(name="Ada", section="bass")

        response = self.client.get(f"/members/{member.pk}/edit/")

        self.assertContains(response, 'value="Ada"')

    def test_ro3_admin_sees_every_member_in_the_list(self):
        make_member(name="Ada", section="bass")
        make_member(name="Grace", section="alto")

        response = self.client.get("/members/")

        self.assertContains(response, "Ada")
        self.assertContains(response, "Grace")

    def test_ro3_admin_opens_the_detail_page_of_a_member_in_any_section(self):
        for section in ["soprano", "alto", "tenor", "bass"]:
            member = make_member(name=f"Member {section}", section=section)

            response = self.client.get(f"/members/{member.pk}/")

            self.assertContains(response, f"Member {section}")


class SectionLeaderTests(TestCase):
    def setUp(self):
        self.alto = make_member(name="Alice Alto", section="alto")
        self.tenor = make_member(name="Tom Tenor", section="tenor")
        self.bass = make_member(name="Bea Bass", section="bass")
        self.soprano = make_member(name="Sue Soprano", section="soprano")
        self.leader = Account.objects.create_user("alto@example.com", sections=["alto"])
        self.client.force_login(self.leader)

    def test_ro3_leader_list_holds_only_their_own_sections_members(self):
        response = self.client.get("/members/")

        self.assertContains(response, "Alice Alto")
        for hidden in ["Tom Tenor", "Bea Bass", "Sue Soprano"]:
            self.assertNotContains(response, hidden)

    def test_ro3_a_leader_with_two_sections_sees_both(self):
        self.leader.sections = ["tenor", "bass"]
        self.leader.save()

        response = self.client.get("/members/")

        self.assertContains(response, "Tom Tenor")
        self.assertContains(response, "Bea Bass")
        self.assertNotContains(response, "Alice Alto")

    def test_ro3_a_leader_with_no_sections_sees_an_empty_list(self):
        self.leader.sections = []
        self.leader.save()

        response = self.client.get("/members/")

        self.assertContains(response, "No members to show")

    def test_ro3_leader_opens_a_detail_page_for_their_own_section(self):
        response = self.client.get(f"/members/{self.alto.pk}/")

        self.assertContains(response, "Alice Alto")

    def test_ro3_leader_gets_not_found_for_another_sections_member(self):
        self.assertEqual(self.client.get(f"/members/{self.tenor.pk}/").status_code, 404)

    def test_ro3_leader_gets_not_found_for_the_add_and_edit_pages(self):
        for url in ["/members/new/", f"/members/{self.alto.pk}/edit/", f"/members/{self.tenor.pk}/edit/"]:
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_ro3_leader_cannot_post_to_the_add_or_edit_pages(self):
        self.client.post("/members/new/", {"name": "Sneaky", "initial_section": "alto"})
        response = self.client.post(f"/members/{self.alto.pk}/edit/", {"name": "Renamed"})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Member.objects.filter(name="Sneaky").exists())
        self.alto.refresh_from_db()
        self.assertEqual(self.alto.name, "Alice Alto")

    def test_ro3_leader_pages_show_no_add_or_edit_controls(self):
        for url in ["/members/", f"/members/{self.alto.pk}/"]:
            response = self.client.get(url)
            self.assertNotContains(response, "Add member")
            self.assertNotContains(response, "/edit/")


class LeaderStatusTests(TestCase):
    def setUp(self):
        self.alto = make_member(name="Alice Alto", section="alto")
        self.tenor = make_member(name="Tom Tenor", section="tenor")
        StatusChange.objects.create(member=self.alto, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.alto, status="on_break", effective_on=date(2026, 6, 1))
        self.client.force_login(Account.objects.create_user("alto@example.com", sections=["alto"]))

    def test_ro3_leader_sees_current_status_and_history_for_their_own_member(self):
        response = self.client.get(f"/members/{self.alto.pk}/")

        self.assertContains(response, "On Break</strong> since Jun 1, 2026. Before that: Active.")
        history = self.client.get(f"/members/{self.alto.pk}/status-history/")
        for shown in ["Jan 5, 2026", "Jun 1, 2026"]:
            self.assertContains(history, shown)

    def test_ro3_leader_gets_not_found_for_another_sections_full_history(self):
        self.assertEqual(self.client.get(f"/members/{self.tenor.pk}/status-history/").status_code, 404)

    def test_ro3_leader_gets_not_found_for_the_change_status_page_on_get_and_post(self):
        for member in [self.alto, self.tenor]:
            url = f"/members/{member.pk}/status/"
            self.assertEqual(self.client.get(url).status_code, 404, url)
            response = self.client.post(url, {"status": "inactive", "effective_on": today().isoformat()})
            self.assertEqual(response.status_code, 404, url)
        self.assertEqual(self.alto.current_status, "on_break")

    def test_ro3_leader_sees_no_change_status_control(self):
        self.assertNotContains(self.client.get(f"/members/{self.alto.pk}/"), f'href="/members/{self.alto.pk}/status/"')


class SignedOutTests(TestCase):
    def test_signed_out_visitors_are_sent_to_sign_in_from_every_member_page(self):
        member = make_member(name="Ada", section="bass")

        for url in ["/members/", "/members/new/", f"/members/{member.pk}/", f"/members/{member.pk}/edit/", f"/members/{member.pk}/status/", f"/members/{member.pk}/status-history/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response["Location"].startswith("/signin/"), url)


class HeaderLinkTests(TestCase):
    def test_signed_in_admins_and_leaders_get_a_members_link_in_the_header(self):
        for account in [
            Account.objects.create_superuser("admin@example.com"),
            Account.objects.create_user("leader@example.com", sections=["alto"]),
        ]:
            self.client.force_login(account)

            response = self.client.get("/members/")

            self.assertContains(response, 'href="/members/"', msg_prefix=account.email)


class MemberAdminTests(TestCase):
    def test_ro3_admin_can_see_members_in_the_django_admin(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        make_member(name="Grace Hopper", section="alto")

        response = self.client.get("/admin/roster/member/")

        self.assertContains(response, "Grace Hopper")


class StatusHistoryTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Ada", section="bass")

    def test_ro2_detail_describes_the_last_change_in_a_sentence(self):
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.member, status="on_break", effective_on=date(2026, 6, 1))

        response = self.client.get(f"/members/{self.member.pk}/")

        self.assertEqual(self.member.current_status, "on_break")
        self.assertContains(response, "On Break</strong> since Jun 1, 2026. Before that: Active.")
        # The older date lives on the full-history page, not here.
        self.assertNotContains(response, "Jan 5, 2026")

    def test_ro2_a_member_with_one_status_has_no_before_that(self):
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))

        response = self.client.get(f"/members/{self.member.pk}/")

        self.assertContains(response, "Active</strong> since Jan 5, 2026.")
        self.assertNotContains(response, "Before that")

    def test_ro2_full_history_lists_every_change_newest_date_first(self):
        for status, day in [("active", date(2026, 1, 5)), ("on_break", date(2026, 6, 1)), ("active", date(2026, 8, 2))]:
            StatusChange.objects.create(member=self.member, status=status, effective_on=day)

        response = self.client.get(f"/members/{self.member.pk}/status-history/")

        content = response.content.decode()
        self.assertLess(content.index("Aug 2, 2026"), content.index("Jun 1, 2026"))
        self.assertLess(content.index("Jun 1, 2026"), content.index("Jan 5, 2026"))
        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), f"/members/{self.member.pk}/status-history/")

    def test_ro2_current_status_is_the_latest_by_date_not_the_last_entered(self):
        StatusChange.objects.create(member=self.member, status="on_break", effective_on=date(2026, 6, 1))
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))

        self.assertEqual(self.member.current_status, "on_break")

    def test_ro2_two_changes_on_one_date_are_kept_and_the_last_entered_is_current(self):
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 6, 1))
        StatusChange.objects.create(member=self.member, status="inactive", effective_on=date(2026, 6, 1))

        self.assertEqual(self.member.current_status, "inactive")
        self.assertEqual(self.member.status_changes.count(), 2)


class ChangeStatusTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Ada", section="bass")
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))
        self.url = f"/members/{self.member.pk}/status/"

    def test_ro2_admin_changes_status_with_todays_date_and_the_detail_page_shows_it(self):
        response = self.client.post(self.url, {"status": "on_break", "effective_on": today().isoformat()})

        self.assertRedirects(response, f"/members/{self.member.pk}/")
        self.assertEqual(self.member.current_status, "on_break")
        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), "On Break")

    def test_ro2_the_form_starts_on_todays_date(self):
        response = self.client.get(self.url)

        self.assertContains(response, f'value="{today().isoformat()}"')

    def test_ro2_a_value_other_than_the_three_statuses_is_rejected(self):
        response = self.client.post(self.url, {"status": "retired", "effective_on": today().isoformat()})

        self.assertContains(response, "Select a valid choice")
        self.assertEqual(self.member.status_changes.count(), 1)

    def test_ro2_admin_can_pick_a_past_date_and_history_stays_newest_date_first(self):
        self.client.post(self.url, {"status": "inactive", "effective_on": "2026-03-01"})
        self.client.post(self.url, {"status": "on_break", "effective_on": "2026-02-01"})

        dates = [c.effective_on for c in self.member.status_history()]
        self.assertEqual(dates, [date(2026, 3, 1), date(2026, 2, 1), date(2026, 1, 5)])
        # Entering an older change later leaves the current status alone.
        self.assertEqual(self.member.current_status, "inactive")

    def test_ro2_two_changes_on_the_same_date_are_both_saved(self):
        self.client.post(self.url, {"status": "on_break", "effective_on": "2026-03-01"})
        self.client.post(self.url, {"status": "active", "effective_on": "2026-03-01"})

        self.assertEqual(self.member.status_changes.filter(effective_on=date(2026, 3, 1)).count(), 2)
        self.assertEqual(self.member.current_status, "active")

    def test_ro2_a_future_date_is_rejected_with_a_clear_message(self):
        tomorrow = today() + timedelta(days=1)

        response = self.client.post(self.url, {"status": "on_break", "effective_on": tomorrow.isoformat()})

        self.assertContains(response, "be in the future")
        self.assertEqual(self.member.status_changes.count(), 1)

    def test_ro2_a_missing_date_is_rejected(self):
        response = self.client.post(self.url, {"status": "on_break", "effective_on": ""})

        self.assertContains(response, "This field is required")
        self.assertEqual(self.member.status_changes.count(), 1)


class EasternTimeTests(TestCase):
    """RO-2: "today" is the US Eastern date, not the server's UTC date."""

    # 03:30 UTC on Oct 25 is 11:30pm on Oct 24 in New York, so the two dates differ.
    LATE_EVENING = datetime(2026, 10, 25, 3, 30, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Ada", section="bass")
        self.url = f"/members/{self.member.pk}/status/"
        patcher = mock.patch("django.utils.timezone.now", return_value=self.LATE_EVENING)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ro2_the_change_form_defaults_to_the_eastern_date(self):
        self.assertContains(self.client.get(self.url), 'value="2026-10-24"')

    def test_ro2_the_utc_date_counts_as_the_future_in_eastern_time(self):
        response = self.client.post(self.url, {"status": "on_break", "effective_on": "2026-10-25"})

        self.assertContains(response, "be in the future")
        self.assertFalse(self.member.status_changes.exists())

    def test_ro2_the_eastern_date_is_accepted(self):
        self.client.post(self.url, {"status": "on_break", "effective_on": "2026-10-24"})

        self.assertEqual(self.member.status_changes.get().effective_on, date(2026, 10, 24))

    def test_ro2_a_new_member_starts_on_the_eastern_date(self):
        self.client.post("/members/new/", {"name": "Grace", "initial_section": "alto"})

        self.assertEqual(Member.objects.get(name="Grace").status_changes.get().effective_on, date(2026, 10, 24))


class InitialStatusTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_ro2_a_new_member_defaults_to_active_dated_today(self):
        self.client.post("/members/new/", {"name": "Ada", "initial_section": "bass", "initial_status": "active"})

        change = Member.objects.get().status_changes.get()
        self.assertEqual((change.status, change.effective_on), ("active", today()))

    def test_ro2_the_add_form_offers_status_with_active_selected(self):
        response = self.client.get("/members/new/")

        self.assertContains(response, "Status")
        self.assertContains(response, '<option value="active" selected>')

    def test_ro2_status_comes_just_above_section_on_the_add_form(self):
        content = self.client.get("/members/new/").content.decode()

        order = [content.index(f'name="{name}"') for name in ["name", "phone", "email", "initial_status", "initial_section"]]
        self.assertEqual(order, sorted(order))

    def test_ro2_a_new_member_can_start_on_another_status(self):
        self.client.post("/members/new/", {"name": "Ada", "initial_section": "bass", "initial_status": "on_break"})

        self.assertEqual(Member.objects.get().current_status, "on_break")

    def test_ro2_a_member_is_not_saved_when_the_initial_status_is_invalid(self):
        response = self.client.post("/members/new/", {"name": "Ada", "initial_section": "bass", "initial_status": "retired"})

        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Member.objects.exists())

    def test_ro2_editing_a_member_does_not_add_a_status_change(self):
        member = make_member(name="Ada", section="bass")
        StatusChange.objects.create(member=member, status="on_break", effective_on=date(2026, 1, 5))

        response = self.client.post(f"/members/{member.pk}/edit/", {"name": "Ada L"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(member.status_changes.count(), 1)
        self.assertNotContains(self.client.get(f"/members/{member.pk}/edit/"), "initial_status")


class BackfillMigrationTests(TestCase):
    def test_ro2_the_migration_gives_an_existing_member_an_active_status_dated_that_day(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module("roster.migrations.0002_statuschange")
        lonely = make_member(name="Had no status", section="alto")
        keeps = make_member(name="Already set", section="bass")
        StatusChange.objects.create(member=keeps, status="inactive", effective_on=date(2026, 1, 5))

        migration.give_existing_members_an_active_status(apps, None)

        change = lonely.status_changes.get()
        self.assertEqual((change.status, change.effective_on), ("active", today()))
        # A member who already has a status is left alone.
        self.assertEqual(keeps.current_status, "inactive")
        self.assertEqual(keeps.status_changes.count(), 1)


class SectionMigrationTests(TransactionTestCase):
    """RO-6: the real migration, run forward over a member who has the old plain fields."""

    def test_ro6_the_migration_turns_each_members_old_section_and_flag_into_changes_dated_that_day(self):
        executor = MigrationExecutor(connection)
        before, after = [("roster", "0002_statuschange")], executor.loader.graph.leaf_nodes("roster")
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(after))
        executor.migrate(before)  # back to the old shape, with section and praise_team on Member
        OldMember = executor.loader.project_state(before).apps.get_model("roster", "Member")
        OldMember.objects.create(name="On Team", section="tenor", praise_team=True)
        OldMember.objects.create(name="Off Team", section="bass", praise_team=False)

        executor = MigrationExecutor(connection)
        executor.migrate(after)

        on, off = Member.objects.get(name="On Team"), Member.objects.get(name="Off Team")
        for member, section, flag in [(on, "tenor", True), (off, "bass", False)]:
            section_change, flag_change = member.section_changes.get(), member.praise_team_changes.get()
            self.assertEqual((section_change.section, section_change.effective_on), (section, today()))
            self.assertEqual((flag_change.praise_team, flag_change.effective_on), (flag, today()))


class StatusAdminTests(TestCase):
    """RO-2: status changes are reached in the Django admin only through a member."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Grace Hopper", section="alto")
        self.other = make_member(name="Ada Lovelace", section="bass")
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.member, status="on_break", effective_on=date(2026, 6, 1))
        StatusChange.objects.create(member=self.other, status="inactive", effective_on=date(2026, 3, 3))
        self.list_url = f"/admin/roster/statuschange/?member__id__exact={self.member.pk}"

    def test_ro2_the_member_page_links_to_only_their_status_changes(self):
        response = self.client.get(f"/admin/roster/member/{self.member.pk}/change/")

        self.assertContains(response, "2 status changes")
        self.assertContains(response, f"member__id__exact={self.member.pk}")

    def test_ro2_the_status_changes_page_lists_only_that_members_rows(self):
        response = self.client.get(self.list_url)

        self.assertContains(response, "June 1, 2026")
        self.assertContains(response, "Jan. 5, 2026")
        self.assertNotContains(response, "March 3, 2026")

    def test_ro2_opening_the_status_changes_page_without_a_member_goes_to_the_members_list(self):
        response = self.client.get("/admin/roster/statuschange/")

        self.assertRedirects(response, "/admin/roster/member/", fetch_redirect_response=False)

    def test_ro2_status_changes_are_not_listed_on_the_admin_home_page(self):
        response = self.client.get("/admin/")

        self.assertContains(response, "/admin/roster/member/")
        self.assertNotContains(response, "/admin/roster/statuschange/")

    def test_ro2_the_django_admin_applies_the_must_change_rule(self):
        response = self.client.post(
            "/admin/roster/statuschange/add/",
            {"member": self.member.pk, "status": "on_break", "effective_on": "2026-07-01"},
        )

        self.assertContains(response, "already On Break")
        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_the_django_admin_rejects_a_future_date_too(self):
        tomorrow = today() + timedelta(days=1)

        response = self.client.post(
            "/admin/roster/statuschange/add/",
            {"member": self.member.pk, "status": "active", "effective_on": tomorrow.isoformat()},
        )

        self.assertContains(response, "be in the future")
        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_a_member_added_in_the_django_admin_starts_active_dated_today(self):
        response = self.client.post(
            "/admin/roster/member/add/", {"name": "New Singer", "initial_section": "tenor", "phone": "", "email": "", "notes": ""}
        )

        self.assertEqual(response.status_code, 302)
        change = Member.objects.get(name="New Singer").status_changes.get()
        self.assertEqual((change.status, change.effective_on), ("active", today()))

    def test_ro2_editing_a_member_in_the_django_admin_adds_no_status_change(self):
        self.client.post(
            f"/admin/roster/member/{self.member.pk}/change/",
            {"name": "Grace H", "section": "alto", "phone": "", "email": "", "notes": ""},
        )

        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_saving_in_the_admin_returns_to_that_members_status_changes(self):
        response = self.client.post(
            "/admin/roster/statuschange/add/",
            {"member": self.member.pk, "status": "active", "effective_on": "2026-07-01"},
        )

        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
        self.assertEqual(self.member.current_status, "active")


class DetailQueryTests(TestCase):
    def test_ro2_the_detail_page_reads_the_status_history_once(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        member = make_member(name="Ada", section="bass")
        for day in (1, 2, 3):
            StatusChange.objects.create(member=member, status="active", effective_on=date(2026, 1, day))

        with CaptureQueriesContext(connection) as queries:
            self.client.get(f"/members/{member.pk}/")

        status_queries = [q for q in queries if "roster_statuschange" in q["sql"]]
        self.assertEqual(len(status_queries), 1)


class MustChangeRuleTests(TestCase):
    """RO-2: a status change that changes nothing is pointless, so it is rejected."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Ada", section="bass")
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.member, status="inactive", effective_on=date(2026, 6, 1))
        self.url = f"/members/{self.member.pk}/status/"

    def post(self, status, on):
        return self.client.post(self.url, {"status": status, "effective_on": on})

    def test_ro2_the_same_status_as_the_one_in_effect_is_rejected_and_names_it(self):
        response = self.post("active", "2026-03-01")

        self.assertContains(response, "Ada is already Active on Mar 1, 2026")
        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_the_same_status_as_the_current_one_is_rejected_today(self):
        response = self.post("inactive", today().isoformat())

        self.assertContains(response, "already Inactive")
        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_a_change_matching_the_next_later_change_is_rejected(self):
        # Inactive is already coming on Jun 1, so Inactive on Mar 1 would make that row pointless.
        response = self.post("inactive", "2026-03-01")

        self.assertContains(response, "Jun 1, 2026")
        self.assertContains(response, "would change nothing")
        self.assertEqual(self.member.status_changes.count(), 2)

    def test_ro2_a_back_dated_change_that_differs_on_both_sides_is_saved(self):
        self.post("on_break", "2026-03-01")

        self.assertEqual(self.member.status_changes.count(), 3)

    def test_ro2_a_same_date_change_must_differ_from_the_one_entered_before_it(self):
        self.post("on_break", "2026-07-01")

        self.assertContains(self.post("on_break", "2026-07-01"), "already On Break")
        self.post("active", "2026-07-01")
        self.assertEqual(self.member.current_status, "active")

    def test_ro2_the_first_status_of_a_member_with_none_can_be_anything(self):
        fresh = make_member(name="New", section="alto")

        response = self.client.post(f"/members/{fresh.pk}/status/", {"status": "inactive", "effective_on": "2026-02-01"})

        self.assertEqual(response.status_code, 302)


class SectionAndPraiseTeamLookupTests(TestCase):
    """RO-6: what a member's section or Praise Team flag was on any date, for later issues to use."""

    def setUp(self):
        self.member = Member.objects.create(name="Ada")

    def test_ro6_section_on_a_date_is_the_latest_change_on_or_before_it(self):
        SectionChange.objects.create(member=self.member, section="alto", effective_on=date(2026, 1, 5))
        SectionChange.objects.create(member=self.member, section="soprano", effective_on=date(2026, 6, 1))

        self.assertIsNone(self.member.section_on(date(2026, 1, 4)))  # before the first change
        self.assertEqual(self.member.section_on(date(2026, 1, 5)), "alto")  # the day it starts
        self.assertEqual(self.member.section_on(date(2026, 5, 31)), "alto")  # between changes
        self.assertEqual(self.member.section_on(date(2026, 6, 1)), "soprano")
        self.assertEqual(self.member.section_on(today()), "soprano")

    def test_ro6_two_section_changes_on_one_date_go_to_the_last_entered(self):
        SectionChange.objects.create(member=self.member, section="alto", effective_on=date(2026, 6, 1))
        SectionChange.objects.create(member=self.member, section="tenor", effective_on=date(2026, 6, 1))

        self.assertEqual(self.member.section_on(date(2026, 6, 1)), "tenor")
        self.assertEqual(self.member.current_section, "tenor")

    def test_ro6_the_current_section_is_the_latest_by_date_not_the_last_entered(self):
        SectionChange.objects.create(member=self.member, section="soprano", effective_on=date(2026, 6, 1))
        SectionChange.objects.create(member=self.member, section="alto", effective_on=date(2026, 1, 5))

        self.assertEqual(self.member.current_section, "soprano")

    def test_ro6_praise_team_on_a_date_is_the_latest_change_on_or_before_it(self):
        PraiseTeamChange.objects.create(member=self.member, praise_team=True, effective_on=date(2026, 3, 1))
        PraiseTeamChange.objects.create(member=self.member, praise_team=False, effective_on=date(2026, 9, 1))

        self.assertFalse(self.member.praise_team_on(date(2026, 2, 28)))  # no change yet means not on it
        self.assertTrue(self.member.praise_team_on(date(2026, 3, 1)))
        self.assertTrue(self.member.praise_team_on(date(2026, 8, 31)))
        self.assertFalse(self.member.praise_team_on(date(2026, 9, 1)))
        self.assertFalse(self.member.current_praise_team)

    def test_ro6_two_praise_team_changes_on_one_date_go_to_the_last_entered_and_today_counts(self):
        PraiseTeamChange.objects.create(member=self.member, praise_team=True, effective_on=date(2026, 6, 1))
        PraiseTeamChange.objects.create(member=self.member, praise_team=False, effective_on=date(2026, 6, 1))
        PraiseTeamChange.objects.create(member=self.member, praise_team=True, effective_on=today())

        self.assertFalse(self.member.praise_team_on(date(2026, 6, 1)))
        self.assertTrue(self.member.praise_team_on(today()))
        self.assertTrue(self.member.current_praise_team)

    def test_ro6_a_member_with_no_section_change_has_no_section(self):
        self.assertIsNone(self.member.current_section)
        self.assertIsNone(self.member.section_on(today()))


class MemberListStatusTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def add(self, name, section, *statuses, praise_team=False):
        member = make_member(name=name, section=section, praise_team=praise_team)
        for i, status in enumerate(statuses):
            StatusChange.objects.create(member=member, status=status, effective_on=date(2026, 1, 1 + i))
        return member

    def test_ro2_the_list_is_grouped_by_section_in_choir_order_with_a_heading_each(self):
        self.add("Bea Bass", "bass", "active")
        self.add("Sue Soprano", "soprano", "active")
        self.add("Tom Tenor", "tenor", "active")
        self.add("Alice Alto", "alto", "active")

        content = self.client.get("/members/").content.decode()

        order = [content.index(f">{heading}</h2>") for heading in ["Soprano", "Alto", "Tenor", "Bass"]]
        self.assertEqual(order, sorted(order))

    def test_ro2_within_a_section_members_are_ordered_by_status_then_name(self):
        self.add("Zed Active", "alto", "active")
        self.add("Amy Inactive", "alto", "active", "inactive")
        self.add("Ben OnBreak", "alto", "active", "on_break")
        self.add("Abe Active", "alto", "active")

        content = self.client.get("/members/?status=all").content.decode()

        names = ["Abe Active", "Zed Active", "Ben OnBreak", "Amy Inactive"]
        positions = [content.index(name) for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_ro2_within_a_status_praise_team_members_come_before_others_then_by_name(self):
        self.add("Abe Plain", "alto", "active")
        self.add("Zed Team", "alto", "active", praise_team=True)
        self.add("Cal Team", "alto", "active", praise_team=True)
        self.add("Bob Plain", "alto", "active")

        content = self.client.get("/members/").content.decode()

        names = ["Cal Team", "Zed Team", "Abe Plain", "Bob Plain"]
        positions = [content.index(name) for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_ro2_a_section_leader_sees_the_same_order_and_dots(self):
        self.add("Abe Plain", "alto", "active")
        self.add("Zed Team", "alto", "active", praise_team=True)
        self.client.force_login(Account.objects.create_user("alto@example.com", sections=["alto"]))

        response = self.client.get("/members/")

        content = response.content.decode()
        self.assertLess(content.index("Zed Team"), content.index("Abe Plain"))
        self.assertContains(response, '<span class="status-dot status-dot-active" aria-hidden="true"></span>Active</span>', count=2)

    def test_ro2_status_still_outranks_praise_team(self):
        self.add("Amy Active", "alto", "active")
        self.add("Ivy Inactive Team", "alto", "active", "inactive", praise_team=True)

        content = self.client.get("/members/?status=all").content.decode()

        self.assertLess(content.index("Amy Active"), content.index("Ivy Inactive Team"))

    def test_ro2_praise_team_order_uses_the_current_flag_not_an_old_one(self):
        self.add("Abe Plain", "alto", "active")
        left = self.add("Zed Left", "alto", "active", praise_team=True)
        PraiseTeamChange.objects.create(member=left, praise_team=False, effective_on=date(2026, 2, 1))

        content = self.client.get("/members/").content.decode()

        self.assertLess(content.index("Abe Plain"), content.index("Zed Left"))

    def test_ro2_each_status_badge_has_its_own_decorative_dot_on_the_list_and_the_member_page(self):
        for status, label in [("active", "Active"), ("on_break", "On Break"), ("inactive", "Inactive")]:
            member = self.add(f"Member {status}", "alto", status)
            dot = f'<span class="status-dot status-dot-{status}" aria-hidden="true"></span>{label}</span>'
            with self.subTest(status=status):
                self.assertContains(self.client.get("/members/?status=all"), dot)
                self.assertContains(self.client.get(f"/members/{member.pk}/"), dot)

    def test_ro2_each_member_shows_their_current_status_not_an_old_one(self):
        self.add("Ben", "alto", "active", "on_break")

        response = self.client.get("/members/")

        self.assertContains(response, ">On Break</span>", count=1)
        self.assertNotContains(response, ">Active</span>")

    def test_ro3_a_leader_sees_headings_only_for_their_own_sections(self):
        self.add("Alice Alto", "alto", "active")
        self.add("Tom Tenor", "tenor", "active")
        self.client.force_login(Account.objects.create_user("alto@example.com", sections=["alto"]))

        response = self.client.get("/members/")

        self.assertContains(response, ">Alto</h2>")
        self.assertNotContains(response, ">Tenor</h2>")
        self.assertContains(response, ">Active</span>")

    def test_ro2_the_list_reads_statuses_in_a_fixed_number_of_queries(self):
        for i in range(2):
            self.add(f"M{i}", "alto", "active")
        with CaptureQueriesContext(connection) as few:
            self.client.get("/members/")
        for i in range(2, 8):
            self.add(f"M{i}", "bass", "active", "on_break")
        with CaptureQueriesContext(connection) as many:
            self.client.get("/members/")

        self.assertEqual(len(few), len(many))


class MemberListFilterTests(TestCase):
    """RO-4: the roster can be filtered by section, status and Praise Team."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def add(self, name, section, status="active", praise_team=False):
        member = make_member(name=name, section=section, praise_team=praise_team)
        StatusChange.objects.create(member=member, status=status, effective_on=date(2026, 1, 1))
        return member

    def test_ro4_with_no_filter_inactive_members_are_hidden_and_the_list_says_so(self):
        self.add("Ada Active", "alto")
        self.add("Ben Break", "alto", "on_break")
        self.add("Ivy Inactive", "alto", "inactive")

        response = self.client.get("/members/")

        self.assertContains(response, "Ada Active")
        self.assertContains(response, "Ben Break")
        self.assertNotContains(response, "Ivy Inactive")
        self.assertContains(response, "Inactive members are hidden")

    def test_ro4_everyone_shows_inactive_members_and_removes_the_notice(self):
        self.add("Ada Active", "alto")
        self.add("Ivy Inactive", "alto", "inactive")

        response = self.client.get("/members/?status=all")

        self.assertContains(response, "Ada Active")
        self.assertContains(response, "Ivy Inactive")
        self.assertNotContains(response, "Inactive members are hidden")

    def test_ro4_the_notice_links_to_the_everyone_view(self):
        self.add("Ivy Inactive", "alto", "inactive")

        response = self.client.get("/members/")

        self.assertContains(response, 'href="/members/?status=all"')

    def test_ro4_the_notice_link_keeps_the_other_filters(self):
        response = self.client.get("/members/?section=alto&praise_team=yes")

        self.assertContains(response, 'href="/members/?section=alto&amp;praise_team=yes&amp;status=all"')

    def test_ro4_each_status_shows_only_members_whose_current_status_matches(self):
        self.add("Ada Active", "alto")
        self.add("Ben Break", "alto", "on_break")
        self.add("Ivy Inactive", "alto", "inactive")
        # Was On Break, now Active again: counts as Active only.
        back = self.add("Ned Returned", "alto", "on_break")
        StatusChange.objects.create(member=back, status="active", effective_on=date(2026, 2, 1))

        for status, shown in [
            ("active", {"Ada Active", "Ned Returned"}),
            ("on_break", {"Ben Break"}),
            ("inactive", {"Ivy Inactive"}),
        ]:
            response = self.client.get(f"/members/?status={status}")
            for name in ["Ada Active", "Ben Break", "Ivy Inactive", "Ned Returned"]:
                if name in shown:
                    self.assertContains(response, name)
                else:
                    self.assertNotContains(response, name)

    def test_ro4_a_section_filter_shows_only_that_sections_heading_and_members(self):
        self.add("Alice Alto", "alto")
        self.add("Tom Tenor", "tenor")

        response = self.client.get("/members/?section=alto")

        self.assertContains(response, "Alice Alto")
        self.assertContains(response, ">Alto</h2>")
        self.assertNotContains(response, "Tom Tenor")
        self.assertNotContains(response, ">Tenor</h2>")

    def test_ro4_a_section_filter_uses_the_section_now_not_an_old_one(self):
        moved = self.add("Mia Mover", "alto")
        SectionChange.objects.create(member=moved, section="tenor", effective_on=date(2026, 3, 1))

        self.assertNotContains(self.client.get("/members/?section=alto"), "Mia Mover")
        self.assertContains(self.client.get("/members/?section=tenor"), "Mia Mover")

    def test_ro4_praise_team_yes_and_no_use_the_current_flag(self):
        self.add("Pat Praise", "alto", praise_team=True)
        self.add("Nell Notteam", "alto", praise_team=False)
        # Joined the team last month: the current flag is what counts.
        joined = self.add("Jo Joiner", "alto", praise_team=False)
        PraiseTeamChange.objects.create(member=joined, praise_team=True, effective_on=today() - timedelta(days=30))

        yes = self.client.get("/members/?praise_team=yes")
        no = self.client.get("/members/?praise_team=no")

        self.assertContains(yes, "Pat Praise")
        self.assertContains(yes, "Jo Joiner")
        self.assertNotContains(yes, "Nell Notteam")
        self.assertContains(no, "Nell Notteam")
        self.assertNotContains(no, "Pat Praise")
        self.assertNotContains(no, "Jo Joiner")

    def test_ro4_section_status_and_praise_team_filters_combine(self):
        self.add("Match Me", "alto", "on_break", praise_team=True)
        self.add("Wrong Section", "tenor", "on_break", praise_team=True)
        self.add("Wrong Status", "alto", "active", praise_team=True)
        self.add("Wrong Team", "alto", "on_break", praise_team=False)

        response = self.client.get("/members/?section=alto&status=on_break&praise_team=yes")

        self.assertContains(response, "Match Me")
        for other in ["Wrong Section", "Wrong Status", "Wrong Team"]:
            self.assertNotContains(response, other)

    def test_ro4_a_value_that_is_not_a_choice_means_no_filter(self):
        self.add("Alice Alto", "alto")
        self.add("Tom Tenor", "tenor")

        response = self.client.get("/members/?section=choir&status=banana&praise_team=maybe")

        self.assertContains(response, "Alice Alto")
        self.assertContains(response, "Tom Tenor")

    def test_ro4_the_page_has_a_labelled_dropdown_per_filter_and_loads_the_script(self):
        response = self.client.get("/members/")

        for name, label in [("section", "Section"), ("status", "Status"), ("praise_team", "Praise Team")]:
            self.assertContains(response, f'<label for="id_{name}"')
            self.assertContains(response, f'<select name="{name}"')
        self.assertContains(response, "members-filter.js")
        # Without JavaScript the form still works through its own button.
        self.assertContains(response, "<noscript>")
        self.assertContains(response, "Apply")

    def test_ro4_the_filter_form_sends_its_choices_in_the_url(self):
        self.assertContains(self.client.get("/members/"), '<form method="get"')

    def test_ro4_the_selected_choices_stay_selected(self):
        response = self.client.get("/members/?section=alto&status=on_break&praise_team=yes")

        self.assertContains(response, '<option value="alto" selected>')
        self.assertContains(response, '<option value="on_break" selected>')
        self.assertContains(response, '<option value="yes" selected>')

    def test_ro4_a_filter_that_matches_nobody_says_so_and_keeps_the_form(self):
        self.add("Alice Alto", "alto")

        response = self.client.get("/members/?section=bass")

        self.assertContains(response, "No members match these filters.")
        self.assertContains(response, '<select name="section"')

    def test_ro4_reset_is_absent_on_the_default_view_and_present_when_a_filter_differs(self):
        self.assertNotContains(self.client.get("/members/"), ">Reset</a>")
        for query in ["section=alto", "status=on_break", "status=all", "praise_team=no"]:
            response = self.client.get(f"/members/?{query}")
            self.assertContains(response, 'href="/members/?section=&amp;status=&amp;praise_team=" class="link">Reset</a>')

    def test_ro4_a_filter_set_to_its_default_does_not_show_reset(self):
        self.assertNotContains(self.client.get("/members/?section=&status=&praise_team="), ">Reset</a>")

    def test_ro4_the_list_reads_the_same_number_of_queries_with_many_members_filtered_or_not(self):
        for query in ["", "?section=alto&status=all&praise_team=yes"]:
            self.add("First", "alto", praise_team=True)
            # RO-4: choosing filters saves them in the session (a write), so save them before counting reads.
            self.client.get(f"/members/{query}")
            with CaptureQueriesContext(connection) as few:
                self.client.get(f"/members/{query}")
            for i in range(6):
                self.add(f"M{i}", "alto", "on_break", praise_team=True)
            with CaptureQueriesContext(connection) as many:
                self.client.get(f"/members/{query}")

            self.assertEqual(len(few), len(many))


class RememberedFilterTests(TestCase):
    """RO-4: the filters a person chose are remembered until Reset or sign-out."""

    def setUp(self):
        self.admin = Account.objects.create_superuser("admin@example.com")
        self.client.force_login(self.admin)
        self.ada = self.add("Ada Active", "alto")
        self.ivy = self.add("Ivy Inactive", "alto", "inactive")
        self.tom = self.add("Tom Tenor", "tenor", "inactive")

    def add(self, name, section, status="active"):
        member = make_member(name=name, section=section)
        StatusChange.objects.create(member=member, status=status, effective_on=date(2026, 1, 1))
        return member

    def assertShowsInactiveAltos(self, response):
        self.assertContains(response, "Ivy Inactive")
        self.assertNotContains(response, "Ada Active")
        self.assertNotContains(response, "Tom Tenor")

    def assertDefaultView(self, response):
        self.assertContains(response, "Ada Active")
        self.assertNotContains(response, "Ivy Inactive")
        self.assertContains(response, "Inactive members are hidden")

    def test_ro4_chosen_filters_are_still_there_after_opening_a_member_and_coming_back(self):
        self.client.get("/members/?section=alto&status=inactive&praise_team=")
        self.client.get(f"/members/{self.ivy.pk}/")

        self.assertShowsInactiveAltos(self.client.get("/members/"))

    def test_ro4_chosen_filters_survive_a_status_change_and_its_redirect(self):
        self.client.get("/members/?section=alto&status=inactive")

        response = self.client.post(
            f"/members/{self.ivy.pk}/status/", {"status": "active", "effective_on": today().isoformat()}
        )
        self.assertRedirects(response, f"/members/{self.ivy.pk}/")

        # Ivy is Active now, so the Inactive filter is empty, but it is still the filter in force.
        response = self.client.get("/members/")
        self.assertContains(response, 'value="inactive" selected')
        self.assertContains(response, "No members match these filters.")

    def test_ro4_filters_in_the_url_replace_the_remembered_ones(self):
        self.client.get("/members/?section=alto&status=inactive")

        self.client.get("/members/?section=tenor&status=all")
        response = self.client.get("/members/")

        self.assertContains(response, "Tom Tenor")
        self.assertNotContains(response, "Ada Active")

    def test_ro4_a_url_with_only_some_filters_sends_the_others_back_to_default(self):
        self.client.get("/members/?section=alto&status=all")

        self.client.get("/members/?status=inactive")
        response = self.client.get("/members/")

        # Section went back to "All sections", so Tom shows too.
        self.assertContains(response, "Ivy Inactive")
        self.assertContains(response, "Tom Tenor")
        self.assertNotContains(response, "Ada Active")

    def test_ro4_the_reset_link_clears_the_remembered_filters(self):
        self.client.get("/members/?section=alto&status=inactive")
        # The page's Reset link is asserted to be this exact URL in the Reset-link test above.
        self.client.get("/members/?section=&status=&praise_team=")

        self.assertDefaultView(self.client.get("/members/"))

    def test_ro4_signing_out_clears_the_remembered_filters(self):
        self.client.get("/members/?section=alto&status=inactive")

        self.client.post("/signout/")
        self.client.force_login(self.admin)

        self.assertDefaultView(self.client.get("/members/"))

    def test_ro4_one_persons_filters_never_change_what_another_sees(self):
        self.client.get("/members/?section=alto&status=inactive")
        other = self.client_class()
        other.force_login(Account.objects.create_superuser("other@example.com"))

        self.assertDefaultView(other.get("/members/"))
        other.get("/members/?status=all")

        self.assertShowsInactiveAltos(self.client.get("/members/"))

    def test_ro4_a_remembered_section_the_leader_no_longer_has_is_dropped(self):
        leader = Account.objects.create_user("tenor@example.com", sections=["tenor", "alto"])
        self.client.force_login(leader)
        self.client.get("/members/?section=alto&status=all")

        leader.sections = ["tenor"]
        leader.save()
        response = self.client.get("/members/")

        self.assertContains(response, "Tom Tenor")
        self.assertNotContains(response, "Ivy Inactive")

    def test_ro4_the_notice_and_show_everyone_link_still_work_with_remembered_filters(self):
        self.client.get("/members/?section=alto&praise_team=")

        response = self.client.get("/members/")

        self.assertContains(response, "Inactive members are hidden")
        self.assertContains(response, 'href="/members/?section=alto&amp;status=all"')

    def test_ro4_remembered_filters_do_not_add_queries(self):
        # Prime the session first, so neither request below has a session write to count.
        self.client.get("/members/?section=alto&status=inactive")
        with CaptureQueriesContext(connection) as plain:
            self.client.get("/members/?section=alto&status=inactive")
        with CaptureQueriesContext(connection) as remembered:
            self.client.get("/members/")

        self.assertEqual(len(plain), len(remembered))


class LeaderFilterTests(TestCase):
    """RO-4, RO-3: a section leader can only filter within their own sections."""

    def setUp(self):
        for name, section in [("Alice Alto", "alto"), ("Tom Tenor", "tenor"), ("Bea Bass", "bass"), ("Sue Soprano", "soprano")]:
            member = make_member(name=name, section=section, praise_team=True)
            StatusChange.objects.create(member=member, status="active", effective_on=date(2026, 1, 1))
        self.alto_leader = Account.objects.create_user("alto@example.com", sections=["alto"])
        self.two_section_leader = Account.objects.create_user("tenor@example.com", sections=["tenor", "bass"])

    def test_ro4_a_leader_with_two_sections_is_offered_only_those_sections(self):
        self.client.force_login(self.two_section_leader)

        response = self.client.get("/members/")

        self.assertContains(response, '<select name="section"')
        self.assertContains(response, '<option value="tenor">')
        self.assertContains(response, '<option value="bass">')
        self.assertNotContains(response, '<option value="alto">')
        self.assertNotContains(response, '<option value="soprano">')

    def test_ro4_a_leader_with_two_sections_can_filter_between_them(self):
        self.client.force_login(self.two_section_leader)

        response = self.client.get("/members/?section=bass")

        self.assertContains(response, "Bea Bass")
        self.assertNotContains(response, "Tom Tenor")

    def test_ro4_a_leader_with_one_section_gets_no_section_dropdown(self):
        self.client.force_login(self.alto_leader)

        response = self.client.get("/members/")

        self.assertNotContains(response, '<select name="section"')
        self.assertContains(response, '<select name="status"')

    def test_ro4_a_leader_asking_for_a_section_that_is_not_theirs_gets_their_normal_list(self):
        self.client.force_login(self.alto_leader)

        for query in ["section=tenor", "section=alto"]:
            response = self.client.get(f"/members/?{query}")

            self.assertContains(response, "Alice Alto")
            for other in ["Tom Tenor", "Bea Bass", "Sue Soprano"]:
                self.assertNotContains(response, other)
            self.assertNotContains(response, ">Reset</a>")

    def test_ro4_a_leaders_other_filters_only_cover_members_they_can_see(self):
        self.client.force_login(self.two_section_leader)

        response = self.client.get("/members/?praise_team=yes&status=all")

        self.assertContains(response, "Tom Tenor")
        self.assertContains(response, "Bea Bass")
        self.assertNotContains(response, "Alice Alto")
        self.assertNotContains(response, "Sue Soprano")


class ChangeSectionTests(TestCase):
    """RO-6: admins record section changes, each with its date."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member("Ada", "alto", since=date(2026, 1, 5))
        self.url = f"/members/{self.member.pk}/section/"

    def test_ro6_admin_changes_section_with_a_date_and_the_pages_show_it(self):
        response = self.client.post(self.url, {"section": "soprano", "effective_on": "2026-06-01"})

        self.assertRedirects(response, f"/members/{self.member.pk}/")
        self.assertEqual(self.member.current_section, "soprano")
        self.assertEqual(self.member.section_on(date(2026, 5, 31)), "alto")
        detail = self.client.get(f"/members/{self.member.pk}/")
        self.assertContains(detail, "Soprano</strong> since Jun 1, 2026. Before that: Alto.")
        # The member now sits under the Soprano heading in the list.
        content = self.client.get("/members/").content.decode()
        self.assertLess(content.index(">Soprano</h2>"), content.index("Ada"))
        self.assertNotIn(">Alto</h2>", content)

    def test_ro6_the_form_starts_on_todays_date_and_says_the_current_section(self):
        response = self.client.get(self.url)

        self.assertContains(response, f'value="{today().isoformat()}"')
        self.assertContains(response, "Now Alto.")

    def test_ro6_a_future_date_is_rejected(self):
        tomorrow = today() + timedelta(days=1)

        response = self.client.post(self.url, {"section": "soprano", "effective_on": tomorrow.isoformat()})

        self.assertContains(response, "be in the future")
        self.assertEqual(self.member.section_changes.count(), 1)

    def test_ro6_the_same_section_as_the_one_in_effect_is_rejected(self):
        response = self.client.post(self.url, {"section": "alto", "effective_on": "2026-03-01"})

        self.assertContains(response, "Ada is already in Alto on Mar 1, 2026")
        self.assertEqual(self.member.section_changes.count(), 1)

    def test_ro6_a_change_matching_the_next_later_change_is_rejected(self):
        SectionChange.objects.create(member=self.member, section="tenor", effective_on=date(2026, 6, 1))

        response = self.client.post(self.url, {"section": "tenor", "effective_on": "2026-03-01"})

        self.assertContains(response, "The next change, on Jun 1, 2026, is also in Tenor")
        self.assertEqual(self.member.section_changes.count(), 2)

    def test_ro6_a_value_other_than_the_four_sections_is_rejected(self):
        response = self.client.post(self.url, {"section": "descant", "effective_on": "2026-03-01"})

        self.assertContains(response, "Select a valid choice")


class ChangePraiseTeamTests(TestCase):
    """RO-6: admins record joining or leaving the Praise Team, each with its date."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member("Ada", "alto", praise_team=False, since=date(2026, 1, 5))
        self.url = f"/members/{self.member.pk}/praise-team/"

    def test_ro6_admin_adds_a_member_to_the_praise_team_with_a_date(self):
        response = self.client.post(self.url, {"praise_team": "yes", "effective_on": "2026-06-01"})

        self.assertRedirects(response, f"/members/{self.member.pk}/")
        self.assertTrue(self.member.current_praise_team)
        self.assertFalse(self.member.praise_team_on(date(2026, 5, 31)))
        detail = self.client.get(f"/members/{self.member.pk}/")
        self.assertContains(detail, "On the Praise Team</strong> since Jun 1, 2026.")
        self.assertNotContains(detail, "Before that: Not on the Praise Team")
        self.assertContains(detail, "Praise Team</span>")

    def test_ro6_admin_takes_a_member_off_the_praise_team(self):
        self.client.post(self.url, {"praise_team": "yes", "effective_on": "2026-06-01"})

        self.client.post(self.url, {"praise_team": "no", "effective_on": "2026-09-01"})

        self.assertFalse(self.member.current_praise_team)
        self.assertTrue(self.member.praise_team_on(date(2026, 8, 31)))
        detail = self.client.get(f"/members/{self.member.pk}/")
        self.assertNotContains(detail, "Praise Team</span>")
        # Leaving is not shown as a sentence on the member page: only the history page records it.
        self.assertNotContains(detail, "Praise Team</strong>")
        self.assertNotContains(detail, "Not on the Praise Team")
        self.assertContains(self.client.get(f"/members/{self.member.pk}/history/"), "Not on the Praise Team")

    def test_ro6_a_member_who_rejoined_shows_the_latest_join_date(self):
        for flag, day in [(True, date(2026, 3, 1)), (False, date(2026, 5, 1)), (True, date(2026, 8, 2))]:
            PraiseTeamChange.objects.create(member=self.member, praise_team=flag, effective_on=day)

        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), "On the Praise Team</strong> since Aug 2, 2026.")

    def test_ro6_the_form_says_the_current_setting(self):
        self.assertContains(self.client.get(self.url), "Now not on the Praise Team.")

    def test_ro6_a_future_date_is_rejected(self):
        tomorrow = today() + timedelta(days=1)

        response = self.client.post(self.url, {"praise_team": "yes", "effective_on": tomorrow.isoformat()})

        self.assertContains(response, "be in the future")
        self.assertEqual(self.member.praise_team_changes.count(), 1)

    def test_ro6_a_change_that_changes_nothing_is_rejected(self):
        response = self.client.post(self.url, {"praise_team": "no", "effective_on": "2026-03-01"})

        self.assertContains(response, "already not on the Praise Team on Mar 1, 2026")
        self.assertEqual(self.member.praise_team_changes.count(), 1)

    def test_ro6_a_change_matching_the_next_later_change_is_rejected(self):
        PraiseTeamChange.objects.create(member=self.member, praise_team=True, effective_on=date(2026, 6, 1))

        response = self.client.post(self.url, {"praise_team": "yes", "effective_on": "2026-03-01"})

        self.assertContains(response, "would change nothing")
        self.assertEqual(self.member.praise_team_changes.count(), 2)


class CombinedHistoryTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member("Ada", "alto", since=date(2026, 1, 5))
        SectionChange.objects.create(member=self.member, section="soprano", effective_on=date(2026, 6, 1))
        PraiseTeamChange.objects.create(member=self.member, praise_team=True, effective_on=date(2026, 8, 2))

    def test_ro6_the_member_page_links_to_one_page_that_lists_both_histories_newest_first(self):
        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), f"/members/{self.member.pk}/history/")

        content = self.client.get(f"/members/{self.member.pk}/history/").content.decode()

        for shown in ["Alto", "Soprano", "Not on the Praise Team", "On the Praise Team", "Jan 5, 2026", "Jun 1, 2026", "Aug 2, 2026"]:
            self.assertIn(shown, content)
        self.assertLess(content.index("Jun 1, 2026"), content.index("Jan 5, 2026"))

    def test_ro6_a_member_with_no_changes_says_so(self):
        bare = Member.objects.create(name="Bare")

        response = self.client.get(f"/members/{bare.pk}/history/")

        self.assertContains(response, "No section yet.")
        self.assertContains(response, "Not on the Praise Team.")


class MovedMemberLeaderTests(TestCase):
    """RO-3, RO-6: a leader sees a member under the section they are in now."""

    def setUp(self):
        self.member = make_member("Mia Mover", "alto", since=date(2026, 1, 5))
        self.alto_leader = Account.objects.create_user("alto@example.com", sections=["alto"])
        self.soprano_leader = Account.objects.create_user("soprano@example.com", sections=["soprano"])
        SectionChange.objects.create(member=self.member, section="soprano", effective_on=date(2026, 6, 1))

    def test_ro3_after_a_move_the_old_leader_gets_not_found_and_no_listing(self):
        self.client.force_login(self.alto_leader)

        self.assertEqual(self.client.get(f"/members/{self.member.pk}/").status_code, 404)
        self.assertNotContains(self.client.get("/members/"), "Mia Mover")

    def test_ro3_after_a_move_the_new_leader_sees_them(self):
        self.client.force_login(self.soprano_leader)

        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), "Mia Mover")
        self.assertContains(self.client.get("/members/"), "Mia Mover")

    def test_ro3_a_move_dated_back_still_counts_as_the_latest_by_date(self):
        # Entered later, but dated earlier than the move to Soprano, so Soprano stays current.
        SectionChange.objects.create(member=self.member, section="tenor", effective_on=date(2026, 3, 1))
        self.client.force_login(self.soprano_leader)

        self.assertContains(self.client.get(f"/members/{self.member.pk}/"), "Mia Mover")


class LeaderSectionHistoryTests(TestCase):
    def setUp(self):
        self.alto = make_member("Alice Alto", "alto")
        self.tenor = make_member("Tom Tenor", "tenor")
        self.client.force_login(Account.objects.create_user("alto@example.com", sections=["alto"]))

    def test_ro3_leader_sees_both_histories_for_their_own_member(self):
        self.assertContains(self.client.get(f"/members/{self.alto.pk}/history/"), "Alice Alto")

    def test_ro3_leader_gets_not_found_for_another_sections_history(self):
        self.assertEqual(self.client.get(f"/members/{self.tenor.pk}/history/").status_code, 404)

    def test_ro3_leader_gets_not_found_for_both_change_pages_on_get_and_post(self):
        for member in [self.alto, self.tenor]:
            for path, data in [
                ("section", {"section": "bass", "effective_on": today().isoformat()}),
                ("praise-team", {"praise_team": "yes", "effective_on": today().isoformat()}),
            ]:
                url = f"/members/{member.pk}/{path}/"
                self.assertEqual(self.client.get(url).status_code, 404, url)
                self.assertEqual(self.client.post(url, data).status_code, 404, url)
        self.assertEqual(self.alto.current_section, "alto")
        self.assertFalse(self.alto.current_praise_team)

    def test_ro3_leader_sees_no_change_controls(self):
        detail = self.client.get(f"/members/{self.alto.pk}/")

        self.assertNotContains(detail, f'href="/members/{self.alto.pk}/section/"')
        self.assertNotContains(detail, f'href="/members/{self.alto.pk}/praise-team/"')


class AddAndEditSectionTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_ro1_adding_a_member_saves_their_first_section_and_flag_dated_today(self):
        self.client.post("/members/new/", {"name": "Ada", "initial_section": "tenor", "initial_praise_team": "on"})

        member = Member.objects.get()
        section_change, flag_change = member.section_changes.get(), member.praise_team_changes.get()
        self.assertEqual((section_change.section, section_change.effective_on), ("tenor", today()))
        self.assertEqual((flag_change.praise_team, flag_change.effective_on), (True, today()))

    def test_ro1_the_praise_team_box_defaults_to_no(self):
        self.client.post("/members/new/", {"name": "Ada", "initial_section": "tenor"})

        self.assertFalse(Member.objects.get().current_praise_team)
        self.assertEqual(Member.objects.get().praise_team_changes.count(), 1)

    def test_ro1_a_section_is_required_when_adding(self):
        response = self.client.post("/members/new/", {"name": "Ada"})

        self.assertContains(response, "This field is required")
        self.assertFalse(Member.objects.exists())

    def test_ro1_editing_a_member_asks_for_neither_and_changes_neither(self):
        member = make_member("Ada", "bass", praise_team=True)

        page = self.client.get(f"/members/{member.pk}/edit/")
        response = self.client.post(f"/members/{member.pk}/edit/", {"name": "Ada L"})

        self.assertNotContains(page, "initial_section")
        self.assertNotContains(page, "initial_praise_team")
        self.assertEqual(response.status_code, 302)
        self.assertEqual((member.section_changes.count(), member.praise_team_changes.count()), (1, 1))
        self.assertEqual((member.current_section, member.current_praise_team), ("bass", True))

    def test_ro1_a_member_is_not_saved_when_the_section_is_invalid(self):
        response = self.client.post("/members/new/", {"name": "Ada", "initial_section": "descant"})

        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Member.objects.exists())


class SectionSignedOutTests(TestCase):
    def test_signed_out_visitors_are_sent_to_sign_in_from_the_new_member_pages(self):
        member = make_member("Ada", "bass")

        for suffix in ["section/", "praise-team/", "history/"]:
            response = self.client.get(f"/members/{member.pk}/{suffix}")
            self.assertEqual(response.status_code, 302, suffix)
            self.assertTrue(response["Location"].startswith("/signin/"), suffix)


class SectionAdminTests(TestCase):
    """RO-6: section and Praise Team changes are reached in the Django admin only through a member."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member("Grace Hopper", "alto", since=date(2026, 1, 5))
        SectionChange.objects.create(member=self.member, section="soprano", effective_on=date(2026, 6, 1))

    def test_ro6_the_member_page_links_to_each_history(self):
        response = self.client.get(f"/admin/roster/member/{self.member.pk}/change/")

        self.assertContains(response, "2 section changes")
        self.assertContains(response, "1 Praise Team change")
        self.assertContains(response, f"/admin/roster/sectionchange/?member__id__exact={self.member.pk}")

    def test_ro6_the_hidden_pages_list_only_that_members_rows(self):
        other = make_member("Ada Lovelace", "bass", since=date(2026, 3, 3))

        response = self.client.get(f"/admin/roster/sectionchange/?member__id__exact={self.member.pk}")

        self.assertContains(response, "June 1, 2026")
        self.assertNotContains(response, "March 3, 2026")
        self.assertNotEqual(other.pk, self.member.pk)

    def test_ro6_opening_either_page_without_a_member_goes_to_the_members_list(self):
        for model in ["sectionchange", "praiseteamchange"]:
            response = self.client.get(f"/admin/roster/{model}/")

            self.assertRedirects(response, "/admin/roster/member/", fetch_redirect_response=False)

    def test_ro6_the_new_pages_are_not_listed_on_the_admin_home_page(self):
        response = self.client.get("/admin/")

        self.assertNotContains(response, "/admin/roster/sectionchange/")
        self.assertNotContains(response, "/admin/roster/praiseteamchange/")

    def test_ro6_the_django_admin_applies_the_must_change_rule_and_the_future_rule(self):
        same = self.client.post(
            "/admin/roster/sectionchange/add/",
            {"member": self.member.pk, "section": "soprano", "effective_on": "2026-07-01"},
        )
        future = self.client.post(
            "/admin/roster/praiseteamchange/add/",
            {"member": self.member.pk, "praise_team": "on", "effective_on": (today() + timedelta(days=1)).isoformat()},
        )

        self.assertContains(same, "already in Soprano")
        self.assertContains(future, "be in the future")

    def test_ro6_a_member_added_in_the_django_admin_gets_all_three_first_rows(self):
        response = self.client.post(
            "/admin/roster/member/add/",
            {"name": "New Singer", "initial_section": "tenor", "initial_praise_team": "on", "phone": "", "email": "", "notes": ""},
        )

        self.assertEqual(response.status_code, 302)
        member = Member.objects.get(name="New Singer")
        self.assertEqual((member.current_status, member.current_section, member.current_praise_team), ("active", "tenor", True))
        self.assertEqual(member.section_changes.get().effective_on, today())

    def test_ro6_the_admin_add_form_requires_a_section(self):
        response = self.client.post("/admin/roster/member/add/", {"name": "New Singer", "phone": "", "email": "", "notes": ""})

        self.assertContains(response, "This field is required")
        self.assertFalse(Member.objects.filter(name="New Singer").exists())

    def test_ro6_editing_a_member_in_the_django_admin_adds_no_section_or_flag_change(self):
        self.client.post(
            f"/admin/roster/member/{self.member.pk}/change/", {"name": "Grace H", "phone": "", "email": "", "notes": ""}
        )

        self.assertEqual((self.member.section_changes.count(), self.member.praise_team_changes.count()), (2, 1))
        self.assertEqual(Member.objects.get(pk=self.member.pk).name, "Grace H")


class MemberListSectionTests(TestCase):
    def test_ro6_the_list_reads_sections_and_flags_in_a_fixed_number_of_queries(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        for i in range(2):
            make_member(f"M{i}", "alto")
        with CaptureQueriesContext(connection) as few:
            self.client.get("/members/")
        for i in range(2, 8):
            member = make_member(f"M{i}", "bass", praise_team=True)
            SectionChange.objects.create(member=member, section="tenor", effective_on=date(2026, 2, 1))
        with CaptureQueriesContext(connection) as many:
            self.client.get("/members/")

        self.assertEqual(len(few), len(many))

    def test_ro6_the_detail_page_reads_each_history_once(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        member = make_member("Ada", "bass")
        SectionChange.objects.create(member=member, section="alto", effective_on=date(2026, 2, 1))

        with CaptureQueriesContext(connection) as queries:
            self.client.get(f"/members/{member.pk}/")

        for table in ["roster_sectionchange", "roster_praiseteamchange"]:
            self.assertEqual(len([q for q in queries if table in q["sql"]]), 1, table)


class ImportMembersTests(TestCase):
    """RO-5: the one-time CSV import. Run through `call_command`, with small CSV files written here (fake data only)."""

    def run_import(self, text, *, expect_error=False):
        """Write `text` to a temp CSV, run the command, and return what it printed."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "members.csv"
            path.write_text(text, encoding="utf-8")
            out = StringIO()
            if expect_error:
                with self.assertRaises(CommandError) as caught:
                    call_command("import_members", str(path), stdout=out)
                return out.getvalue() + str(caught.exception)
            call_command("import_members", str(path), stdout=out)
            return out.getvalue()

    def test_ro5_import_creates_active_members_with_section_and_flag_dated_today(self):
        self.run_import(
            "name,section,praise_team,phone,email,notes\n"
            "Ada Example,Soprano,yes,555-0101,ada@example.com,Likes hymns\n"
            "Bo Example,Bass,no,,,\n"
        )
        ada = Member.objects.get(name="Ada Example")
        self.assertEqual(ada.phone, "555-0101")
        self.assertEqual(ada.email, "ada@example.com")
        self.assertEqual(ada.notes, "Likes hymns")
        self.assertEqual(ada.current_status, "active")
        self.assertEqual(ada.current_section, "soprano")
        self.assertTrue(ada.current_praise_team)
        self.assertEqual(ada.status_history().get().effective_on, today())
        self.assertEqual(ada.section_history().get().effective_on, today())
        bo = Member.objects.get(name="Bo Example")
        self.assertEqual(bo.current_section, "bass")
        self.assertFalse(bo.current_praise_team)
        self.assertEqual(bo.current_status, "active")

    def test_ro5_optional_columns_can_be_missing_and_section_can_be_any_case(self):
        self.run_import("name,section\nCy Example,aLtO\n")
        cy = Member.objects.get(name="Cy Example")
        self.assertEqual(cy.current_section, "alto")
        self.assertFalse(cy.current_praise_team)
        self.assertEqual((cy.phone, cy.email, cy.notes), ("", "", ""))

    def test_ro5_every_praise_team_spelling_is_understood(self):
        spellings = {"yes": True, "Y": True, "TRUE": True, "1": True, "no": False, "n": False, "false": False, "0": False, "": False}
        rows = "".join(f"Member {i},Tenor,{value}\n" for i, value in enumerate(spellings))
        self.run_import("name,section,praise_team\n" + rows)
        for i, expected in enumerate(spellings.values()):
            self.assertEqual(Member.objects.get(name=f"Member {i}").current_praise_team, expected, list(spellings)[i])

    def test_ro5_a_file_saved_by_excel_with_a_bom_still_works(self):
        self.run_import("﻿name,section\nDi Example,Bass\n")
        self.assertTrue(Member.objects.filter(name="Di Example").exists())

    def test_ro5_every_bad_row_is_listed_by_line_and_nothing_is_imported(self):
        Member.objects.create(name="Existing Person")
        output = self.run_import(
            "name,section,praise_team,phone,email,notes\n"  # line 1: header
            "Good One,Soprano,yes,,,\n"  # line 2: fine
            ",Alto,no,,,\n"  # line 3: missing name
            "Bad Section,Baritone,no,,,\n"  # line 4: unknown section
            "Bad Email,Bass,no,,not-an-email,\n"  # line 5: bad email
            "Bad Flag,Tenor,maybe,,,\n"  # line 6: bad Praise Team value
            "existing person,Alto,no,,,\n"  # line 7: name already on the roster (ignoring case)
            "Twin,Alto,no,,,\n"  # line 8: first Twin is fine
            "TWIN,Alto,no,,,\n",  # line 9: repeated in the file itself
            expect_error=True,
        )
        for line in (3, 4, 5, 6, 7, 9):
            self.assertIn(f"line {line}:", output)
        for line in (1, 2, 8):
            self.assertNotIn(f"line {line}:", output)
        self.assertEqual(list(Member.objects.values_list("name", flat=True)), ["Existing Person"])

    def test_ro5_output_never_includes_names_emails_or_phones(self):
        secrets = ["Zelda Secretname", "zelda.secret@example.com", "555-0199"]
        ok = self.run_import(f"name,section,phone,email\n{secrets[0]},Alto,{secrets[2]},{secrets[1]}\n")
        failed = self.run_import(
            f"name,section,phone,email\n{secrets[0]}2,Nonsense,{secrets[2]},{secrets[1]}\n"
            f"Other Secret,Alto,{secrets[2]},not-an-email\n",
            expect_error=True,
        )
        for text in (ok, failed):
            for secret in secrets + ["Other Secret", "not-an-email", "Nonsense"]:
                self.assertNotIn(secret, text)

    def test_ro5_a_missing_file_is_a_clear_error(self):
        with self.assertRaises(CommandError) as caught:
            call_command("import_members", "/nonexistent/members.csv", stdout=StringIO())
        self.assertIn("not found", str(caught.exception).lower())

    def test_ro5_a_file_without_the_required_columns_imports_nothing(self):
        output = self.run_import("full name,voice\nAda Example,Alto\n", expect_error=True)
        self.assertIn("name", output)
        self.assertIn("section", output)
        self.assertFalse(Member.objects.exists())

    def test_ro5_an_empty_file_is_a_clear_error(self):
        self.run_import("", expect_error=True)
        self.assertFalse(Member.objects.exists())


class DropdownStyleTests(TestCase):
    """Design polish (#49): every <select> gets the shared `select` look and a drawn arrow; other inputs don't."""

    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = make_member(name="Ada Active", section="alto")
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 1))

    def assertSelects(self, response, count):
        """`count` selects on the page, each with the select class and its own arrow."""
        self.assertContains(response, "<select", count=count)
        self.assertContains(response, 'class="select"', count=count)
        self.assertContains(response, "data-select-chevron", count=count)

    def test_the_three_roster_filters_get_the_select_look_and_arrow(self):
        self.assertSelects(self.client.get("/members/"), 3)

    def test_the_add_member_form_selects_get_the_select_look_and_arrow(self):
        # Starting status and section.
        self.assertSelects(self.client.get("/members/new/"), 2)

    def test_each_change_form_select_gets_the_select_look_and_arrow(self):
        for page in ["status", "section", "praise-team"]:
            with self.subTest(page=page):
                self.assertSelects(self.client.get(f"/members/{self.member.pk}/{page}/"), 1)

    def test_other_inputs_get_neither_the_select_class_nor_an_arrow(self):
        response = self.client.get("/members/new/")

        # Name, phone, email and notes keep the text-input look; the checkbox is untouched.
        self.assertContains(response, 'class="input"', count=4)
        self.assertContains(response, 'class="size-6 accent-indigo-600"')
        # The date field on a change form is a plain input too.
        change = self.client.get(f"/members/{self.member.pk}/status/")
        self.assertContains(change, 'type="date"')
        self.assertContains(change, 'class="input"', count=1)

    def test_the_arrow_lets_taps_through_and_is_hidden_from_screen_readers(self):
        # pointer-events-none: a tap on the arrow reaches the select, so the native picker opens.
        # Matched on the arrow's own tag, so the same classes elsewhere on the page can't satisfy it.
        for page in ["/members/", "/members/new/"]:
            with self.subTest(page=page):
                response = self.client.get(page)
                arrows = response.content.decode().count("data-select-chevron")
                self.assertGreater(arrows, 0)
                self.assertContains(response, 'aria-hidden="true" data-select-chevron class="pointer-events-none', count=arrows)

    def test_the_built_css_has_the_select_rule(self):
        # Catches a forgotten `bin/tailwindcss` rebuild: static/app.css is committed, never built on deploy.
        css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text()

        self.assertIn(".select{", css)


def fake_now(year, month, day, hour=12, minute=0, tz="America/New_York"):
    """A fixed clock for the app's `timezone.now()`, given in US Eastern so tests read like the choir's week."""
    from zoneinfo import ZoneInfo

    return mock.patch("django.utils.timezone.now", return_value=datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz)))


class CreateEventsCommandTests(TestCase):
    def test_at1_creates_wednesday_saturday_and_sunday_for_this_week_and_the_next_four(self):
        # Sunday 1 Nov 2026 is in the week of Mon 26 Oct; five weeks end on Sun 29 Nov.
        with fake_now(2026, 11, 1):
            call_command("create_events", stdout=StringIO())

        events = Event.objects.order_by("date")
        self.assertEqual(events.count(), 15)
        self.assertEqual(events.first().date, date(2026, 10, 28))  # the Wednesday of this week
        self.assertEqual(events.last().date, date(2026, 11, 29))
        wednesday = Event.objects.get(date=date(2026, 10, 28))
        self.assertEqual((wednesday.kind, wednesday.expected), (Event.Kind.WEDNESDAY, Event.Expected.PRAISE_TEAM))
        saturday = Event.objects.get(date=date(2026, 10, 31))
        self.assertEqual((saturday.kind, saturday.expected), (Event.Kind.SATURDAY, Event.Expected.EVERYONE))
        sunday = Event.objects.get(date=date(2026, 11, 1))
        self.assertEqual((sunday.kind, sunday.expected), (Event.Kind.SUNDAY, Event.Expected.EVERYONE))

    def test_at1_reports_how_many_it_created(self):
        out = StringIO()
        with fake_now(2026, 11, 1):
            call_command("create_events", stdout=out)

        self.assertIn("Created 15 events.", out.getvalue())

    def test_at1_rerunning_creates_nothing_more(self):
        with fake_now(2026, 11, 1):
            call_command("create_events", stdout=StringIO())
            out = StringIO()
            call_command("create_events", stdout=out)

        self.assertEqual(Event.objects.count(), 15)
        self.assertIn("Created 0 events.", out.getvalue())

    def test_at1_a_canceled_event_is_not_recreated_or_uncanceled(self):
        with fake_now(2026, 11, 1):
            call_command("create_events", stdout=StringIO())
            Event.objects.filter(date=date(2026, 10, 31)).update(canceled=True)
            call_command("create_events", stdout=StringIO())

        saturday = Event.objects.get(date=date(2026, 10, 31))
        self.assertTrue(saturday.canceled)
        self.assertEqual(Event.objects.count(), 15)

    def test_at1_this_week_follows_us_eastern_not_utc(self):
        # 11:30pm Eastern on Sunday 1 Nov is already Monday 2 Nov in UTC, which would start a new week.
        with fake_now(2026, 11, 1, hour=23, minute=30):
            call_command("create_events", stdout=StringIO())

        self.assertEqual(Event.objects.order_by("date").first().date, date(2026, 10, 28))

    def test_at1_the_database_rejects_a_second_saturday_on_one_date(self):
        from django.db import IntegrityError, transaction

        Event.objects.create(date=date(2026, 10, 31), kind=Event.Kind.SATURDAY, expected=Event.Expected.EVERYONE)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.create(date=date(2026, 10, 31), kind=Event.Kind.SATURDAY, expected=Event.Expected.EVERYONE)

    def test_at2_special_events_can_share_a_date(self):
        for name in ["Concert", "Dress run"]:
            Event.objects.create(
                date=date(2026, 12, 5), kind=Event.Kind.SPECIAL, name=name, expected=Event.Expected.EVERYONE
            )

        self.assertEqual(Event.objects.filter(date=date(2026, 12, 5)).count(), 2)


def make_event(day, kind=Event.Kind.SPECIAL, name="Concert", expected=Event.Expected.EVERYONE, **fields):
    return Event.objects.create(date=day, kind=kind, name=name, expected=expected, **fields)


class EventListTests(TestCase):
    def setUp(self):
        self.admin = Account.objects.create_superuser("admin@example.com")
        self.client.force_login(self.admin)

    def test_at1_the_button_creates_events_and_says_how_many(self):
        with fake_now(2026, 11, 1):
            response = self.client.post("/events/create-upcoming/", follow=True)

        self.assertRedirects(response, "/events/")
        self.assertContains(response, "Created 15 events.")
        self.assertEqual(Event.objects.count(), 15)

    def test_at1_pressing_the_button_again_creates_none(self):
        with fake_now(2026, 11, 1):
            self.client.post("/events/create-upcoming/")
            response = self.client.post("/events/create-upcoming/", follow=True)

        self.assertContains(response, "Created 0 events.")

    def test_at1_the_button_does_not_act_on_a_get(self):
        response = self.client.get("/events/create-upcoming/")

        self.assertEqual(response.status_code, 405)
        self.assertFalse(Event.objects.exists())

    def test_at1_the_events_page_has_the_button(self):
        response = self.client.get("/events/")

        self.assertContains(response, "Add the next few weeks of events")
        self.assertNotContains(response, "Create upcoming events")

    def test_at3_the_events_page_lists_today_and_later_in_date_order_and_not_earlier(self):
        make_event(date(2026, 11, 10), name="Later")
        make_event(date(2026, 11, 1), name="Today")
        make_event(date(2026, 10, 30), name="Yesterday")
        make_event(date(2026, 11, 5), name="Between")

        with fake_now(2026, 11, 1):
            body = self.client.get("/events/").content.decode()

        self.assertNotIn("Yesterday", body)
        self.assertLess(body.index("Today"), body.index("Between"))
        self.assertLess(body.index("Between"), body.index("Later"))

    def test_at1_praise_team_events_say_so(self):
        make_event(date(2026, 11, 4), kind=Event.Kind.WEDNESDAY, name="", expected=Event.Expected.PRAISE_TEAM)

        with fake_now(2026, 11, 1):
            response = self.client.get("/events/")

        self.assertContains(response, "Midweek")

    def test_at3_the_events_page_links_to_past_events(self):
        response = self.client.get("/events/")

        self.assertContains(response, 'href="/events/past/"')

    def test_at3_the_past_page_lists_only_earlier_events_newest_first(self):
        make_event(date(2026, 10, 20), name="Oldest")
        make_event(date(2026, 10, 30), name="Newest")
        make_event(date(2026, 11, 1), name="Today")

        with fake_now(2026, 11, 1):
            body = self.client.get("/events/past/").content.decode()

        self.assertLess(body.index("Newest"), body.index("Oldest"))
        self.assertNotIn("Today", body)
        self.assertIn('href="/events/"', body)

    def test_at3_the_header_has_an_events_link_for_admins(self):
        self.assertContains(self.client.get("/members/"), 'href="/events/"')


class EventPermissionTests(TestCase):
    def test_at1_leaders_get_not_found_on_every_events_page(self):
        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))
        event = make_event(date(2026, 12, 5))

        for url in ["/events/", "/events/past/", "/events/new/", f"/events/{event.pk}/cancel/"]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in ["/events/create-upcoming/", "/events/new/", f"/events/{event.pk}/cancel/"]:
            self.assertEqual(self.client.post(url).status_code, 404, url)
        self.assertFalse(Event.objects.filter(canceled=True).exists())

    def test_at1_leaders_have_no_events_link(self):
        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))

        self.assertNotContains(self.client.get("/members/"), 'href="/events/"')

    def test_at1_signed_out_visitors_are_sent_to_sign_in(self):
        event = make_event(date(2026, 12, 5))

        for url in ["/events/", "/events/past/", "/events/new/", f"/events/{event.pk}/cancel/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response["Location"].startswith("/signin/"), url)
        # The actions too: a signed-out POST must not create or cancel anything.
        for url in ["/events/create-upcoming/", "/events/new/", f"/events/{event.pk}/cancel/"]:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response["Location"].startswith("/signin/"), url)
        self.assertEqual(Event.objects.count(), 1)
        self.assertFalse(Event.objects.get().canceled)


class AddEventTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at2_an_admin_adds_a_special_event(self):
        response = self.client.post(
            "/events/new/",
            {"date": "2026-12-05", "kind": "special", "name": "Christmas concert", "expected": "everyone"},
        )

        self.assertRedirects(response, "/events/")
        event = Event.objects.get()
        self.assertEqual((event.date, event.kind, event.name), (date(2026, 12, 5), "special", "Christmas concert"))

    def test_at2_an_admin_adds_an_extra_rehearsal_for_the_praise_team(self):
        self.client.post(
            "/events/new/",
            {"date": "2026-12-02", "kind": "extra", "name": "Band run-through", "expected": "praise_team"},
        )

        event = Event.objects.get()
        self.assertEqual((event.kind, event.expected), ("extra", "praise_team"))

    def test_at2_several_events_can_share_a_date(self):
        for name in ["Concert", "Dress run"]:
            self.client.post("/events/new/", {"date": "2026-12-05", "kind": "special", "name": name, "expected": "everyone"})

        self.assertEqual(Event.objects.filter(date=date(2026, 12, 5)).count(), 2)

    def test_at2_a_name_is_required(self):
        response = self.client.post("/events/new/", {"date": "2026-12-05", "kind": "special", "name": "", "expected": "everyone"})

        self.assertContains(response, "This field is required")
        self.assertFalse(Event.objects.exists())

    def test_at2_a_past_date_is_accepted(self):
        with fake_now(2026, 11, 1):
            response = self.client.post(
                "/events/new/", {"date": "2026-09-01", "kind": "special", "name": "Retreat", "expected": "everyone"}
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.get().date, date(2026, 9, 1))

    def test_at2_the_kind_can_only_be_special_or_extra(self):
        response = self.client.post("/events/new/", {"date": "2026-12-05", "kind": "saturday", "name": "X", "expected": "everyone"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_at2_the_events_page_links_to_the_add_form(self):
        self.assertContains(self.client.get("/events/"), 'href="/events/new/"')
        self.assertContains(self.client.get("/events/new/"), "Special event")


class CancelEventTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at3_the_confirm_page_names_the_event_and_changes_nothing(self):
        event = make_event(date(2026, 11, 7), name="Rehearsal")

        with fake_now(2026, 11, 1):
            response = self.client.get(f"/events/{event.pk}/cancel/")

        self.assertContains(response, "Rehearsal")
        event.refresh_from_db()
        self.assertFalse(event.canceled)

    def test_at3_canceling_marks_the_event_and_keeps_its_place_in_date_order(self):
        first = make_event(date(2026, 11, 3), name="First")
        middle = make_event(date(2026, 11, 7), name="Middle")
        make_event(date(2026, 11, 9), name="Last")

        with fake_now(2026, 11, 1):
            response = self.client.post(f"/events/{middle.pk}/cancel/", follow=True)
            # Only the list: the "is canceled" message above it names the event too.
            body = response.content.decode().split("<ul", 1)[1]

        middle.refresh_from_db()
        self.assertTrue(middle.canceled)
        self.assertRedirects(response, "/events/")
        self.assertIn("Canceled</span>", body)
        self.assertLess(body.index("First"), body.index("Middle"))
        self.assertLess(body.index("Middle"), body.index("Last"))
        self.assertFalse(first.canceled)

    def test_at3_an_event_today_can_be_canceled(self):
        event = make_event(date(2026, 11, 1))

        with fake_now(2026, 11, 1):
            self.client.post(f"/events/{event.pk}/cancel/")

        event.refresh_from_db()
        self.assertTrue(event.canceled)

    def test_at3_a_past_event_cannot_be_canceled(self):
        event = make_event(date(2026, 10, 30))

        with fake_now(2026, 11, 1):
            self.assertEqual(self.client.get(f"/events/{event.pk}/cancel/").status_code, 404)
            self.assertEqual(self.client.post(f"/events/{event.pk}/cancel/").status_code, 404)

        event.refresh_from_db()
        self.assertFalse(event.canceled)

    def test_at3_an_already_canceled_event_cannot_be_canceled_again(self):
        event = make_event(date(2026, 11, 7), canceled=True)

        with fake_now(2026, 11, 1):
            self.assertEqual(self.client.post(f"/events/{event.pk}/cancel/").status_code, 404)

    def test_at3_only_upcoming_events_that_are_not_canceled_offer_a_cancel_button(self):
        live = make_event(date(2026, 11, 7), name="Live")
        gone = make_event(date(2026, 11, 8), name="Gone", canceled=True)
        past = make_event(date(2026, 10, 30), name="Past")

        with fake_now(2026, 11, 1):
            events_page = self.client.get("/events/")
            past_page = self.client.get("/events/past/")

        self.assertContains(events_page, f'href="/events/{live.pk}/cancel/"')
        self.assertNotContains(events_page, f'href="/events/{gone.pk}/cancel/"')
        self.assertNotContains(past_page, f'href="/events/{past.pk}/cancel/"')

    def test_at3_the_past_page_badges_canceled_events(self):
        make_event(date(2026, 10, 30), name="Old", canceled=True)

        with fake_now(2026, 11, 1):
            response = self.client.get("/events/past/")

        self.assertContains(response, "Canceled</span>")


class EventListLayoutTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def page(self, url="/events/", now=(2026, 11, 1)):
        with fake_now(*now):
            return self.client.get(url).content.decode()

    def test_at1_events_are_grouped_under_a_heading_for_each_month_in_date_order(self):
        make_event(date(2026, 12, 5), name="December thing")
        make_event(date(2026, 11, 7), name="November thing")

        body = self.page()

        self.assertLess(body.index("November 2026"), body.index("November thing"))
        self.assertLess(body.index("November thing"), body.index("December 2026"))
        self.assertLess(body.index("December 2026"), body.index("December thing"))

    def test_at3_past_events_are_grouped_by_month_newest_month_first(self):
        make_event(date(2026, 9, 5), name="September thing")
        make_event(date(2026, 10, 3), name="October thing")

        body = self.page("/events/past/")

        self.assertLess(body.index("October 2026"), body.index("October thing"))
        self.assertLess(body.index("October thing"), body.index("September 2026"))

    def test_at1_a_regular_event_shows_its_weekday_and_date_with_the_kind_badge_beside_them(self):
        make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        body = self.page()

        # The badge sits in the same line as the date, not on a line of its own.
        self.assertRegex(body, r'<p[^>]*>\s*Sat, Nov 7\s*<span class="badge">.*?Rehearsal</span>\s*</p>')

    def test_at1_the_kinds_are_called_midweek_rehearsal_and_services(self):
        make_event(date(2026, 11, 4), kind=Event.Kind.WEDNESDAY, name="")
        make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")
        make_event(date(2026, 11, 8), kind=Event.Kind.SUNDAY, name="")

        body = self.page()

        for label in ["Midweek</span>", "Rehearsal</span>", "Services</span>"]:
            self.assertIn(label, body)

    def test_at1_each_regular_kind_has_a_quiet_badge_with_its_own_colored_dot(self):
        make_event(date(2026, 11, 4), kind=Event.Kind.WEDNESDAY, name="")
        make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")
        make_event(date(2026, 11, 8), kind=Event.Kind.SUNDAY, name="")

        body = self.page()

        for kind in ["wednesday", "saturday", "sunday"]:
            self.assertEqual(body.count(f"kind-dot-{kind}"), 1, kind)
        self.assertNotIn("badge-accent", body)

    def test_at2_special_events_and_extra_rehearsals_get_the_same_badge_as_the_praise_team_label(self):
        make_event(date(2026, 12, 5), name="Concert")
        make_event(date(2026, 12, 2), kind=Event.Kind.EXTRA, name="Run-through")

        body = self.page()

        self.assertIn('class="badge-accent">Special event</span>', body)
        self.assertIn('class="badge-accent">Extra rehearsal</span>', body)
        self.assertNotIn("kind-dot", body)

    def test_at2_a_special_event_shows_its_name_its_date_with_weekday_and_a_kind_badge(self):
        make_event(date(2026, 12, 5), name="Christmas concert")

        body = self.page()

        self.assertIn("Christmas concert", body)
        self.assertIn("Sat, Dec 5", body)
        self.assertIn("Special event</span>", body)

    def test_at1_praise_team_events_carry_no_praise_team_note_in_the_list(self):
        make_event(date(2026, 11, 4), kind=Event.Kind.WEDNESDAY, name="", expected=Event.Expected.PRAISE_TEAM)

        body = self.page()

        self.assertNotIn("Praise Team", body)

    def test_at2_event_notes_are_italic(self):
        make_event(date(2026, 11, 7), name="Concert", notes="Wear black")

        self.assertIn('<p class="muted italic">Wear black</p>', self.page())

    def test_at1_the_create_events_button_is_below_the_list_and_explained(self):
        make_event(date(2026, 11, 7), name="Concert")

        body = self.page()

        self.assertLess(body.index("Concert"), body.index("Add the next few weeks of events"))
        self.assertIn("does this by itself every day", body)


class RestoreEventTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at3_the_cancel_page_is_titled_with_the_kind_and_the_date_without_a_weekday(self):
        event = make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        with fake_now(2026, 11, 1):
            response = self.client.get(f"/events/{event.pk}/cancel/")

        self.assertContains(response, "Cancel Rehearsal on Nov 7?")
        self.assertNotContains(response, "Sat,")

    def test_at3_the_cancel_page_button_is_red(self):
        event = make_event(date(2026, 11, 7))

        with fake_now(2026, 11, 1):
            response = self.client.get(f"/events/{event.pk}/cancel/")

        self.assertContains(response, 'class="btn-danger"')

    def test_at3_the_cancel_link_in_a_list_is_a_quiet_red_button(self):
        event = make_event(date(2026, 11, 7))

        with fake_now(2026, 11, 1):
            response = self.client.get("/events/")

        self.assertContains(response, f'href="/events/{event.pk}/cancel/" class="btn-danger-quiet"')

    def test_at3_restoring_a_canceled_upcoming_event_brings_it_back_in_place(self):
        make_event(date(2026, 11, 3), name="First")
        middle = make_event(date(2026, 11, 7), name="Middle", canceled=True)
        make_event(date(2026, 11, 9), name="Last")

        with fake_now(2026, 11, 1):
            confirm = self.client.get(f"/events/{middle.pk}/restore/")
            middle.refresh_from_db()
            still_canceled = middle.canceled
            response = self.client.post(f"/events/{middle.pk}/restore/", follow=True)
            body = response.content.decode().split("<ul", 1)[1]

        self.assertContains(confirm, "Restore Middle on Nov 7?")
        self.assertTrue(still_canceled)
        middle.refresh_from_db()
        self.assertFalse(middle.canceled)
        self.assertRedirects(response, "/events/")
        self.assertNotIn("Canceled</span>", body)
        self.assertLess(body.index("First"), body.index("Middle"))
        self.assertLess(body.index("Middle"), body.index("Last"))

    def test_at3_only_canceled_upcoming_events_offer_restore(self):
        canceled = make_event(date(2026, 11, 7), name="Gone", canceled=True)
        live = make_event(date(2026, 11, 8), name="Live")
        old = make_event(date(2026, 10, 30), name="Old", canceled=True)

        with fake_now(2026, 11, 1):
            events_page = self.client.get("/events/")
            past_page = self.client.get("/events/past/")

        self.assertContains(events_page, f'href="/events/{canceled.pk}/restore/" class="btn-quiet"')
        self.assertNotContains(events_page, f'href="/events/{live.pk}/restore/"')
        self.assertNotContains(past_page, f'href="/events/{old.pk}/restore/"')

    def test_at3_a_past_or_not_canceled_event_cannot_be_restored(self):
        old = make_event(date(2026, 10, 30), canceled=True)
        live = make_event(date(2026, 11, 8))

        with fake_now(2026, 11, 1):
            for event in (old, live):
                self.assertEqual(self.client.get(f"/events/{event.pk}/restore/").status_code, 404)
                self.assertEqual(self.client.post(f"/events/{event.pk}/restore/").status_code, 404)

        old.refresh_from_db()
        self.assertTrue(old.canceled)

    def test_at3_leaders_get_not_found_and_signed_out_visitors_go_to_sign_in(self):
        event = make_event(date(2026, 12, 5), canceled=True)
        self.client.logout()
        response = self.client.post(f"/events/{event.pk}/restore/")
        self.assertTrue(response["Location"].startswith("/signin/"))

        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))
        self.assertEqual(self.client.get(f"/events/{event.pk}/restore/").status_code, 404)
        self.assertEqual(self.client.post(f"/events/{event.pk}/restore/").status_code, 404)
        event.refresh_from_db()
        self.assertTrue(event.canceled)


class ExtraRehearsalNameTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at2_an_extra_rehearsal_does_not_need_a_name(self):
        response = self.client.post(
            "/events/new/", {"date": "2026-12-02", "kind": "extra", "name": "", "expected": "everyone"}
        )

        self.assertRedirects(response, "/events/")
        self.assertEqual(Event.objects.get().name, "")

    def test_at2_an_unnamed_extra_rehearsal_reads_like_a_regular_event_with_its_date_and_badge(self):
        make_event(date(2026, 12, 2), kind=Event.Kind.EXTRA, name="")

        with fake_now(2026, 11, 1):
            body = self.client.get("/events/").content.decode()

        self.assertRegex(body, r'<p[^>]*>\s*Wed, Dec 2\s*<span class="badge-accent">Extra rehearsal</span>\s*</p>')

    def test_at2_a_named_extra_rehearsal_shows_its_name_with_the_date_below(self):
        make_event(date(2026, 12, 2), kind=Event.Kind.EXTRA, name="Band run-through")

        with fake_now(2026, 11, 1):
            body = self.client.get("/events/").content.decode()

        self.assertRegex(body, r'<p[^>]*>\s*Band run-through\s*<span class="badge-accent">Extra rehearsal</span>\s*</p>')

    def test_at2_a_special_event_still_needs_a_name(self):
        response = self.client.post(
            "/events/new/", {"date": "2026-12-05", "kind": "special", "name": "", "expected": "everyone"}
        )

        self.assertContains(response, "This field is required")
        self.assertFalse(Event.objects.exists())


class EventNotesTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at2_notes_are_saved_with_a_new_event(self):
        self.client.post(
            "/events/new/",
            {"date": "2026-12-05", "kind": "special", "name": "Concert", "expected": "everyone", "notes": "Wear black"},
        )

        self.assertEqual(Event.objects.get().notes, "Wear black")

    def test_at2_notes_are_optional(self):
        response = self.client.post(
            "/events/new/", {"date": "2026-12-05", "kind": "special", "name": "Concert", "expected": "everyone"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.get().notes, "")

    def test_at2_notes_show_under_the_date_on_the_events_and_past_pages(self):
        make_event(date(2026, 11, 7), name="Upcoming", notes="Bring folders")
        make_event(date(2026, 10, 30), name="Earlier", notes="Was moved to the hall")

        with fake_now(2026, 11, 1):
            events_page = self.client.get("/events/")
            past_page = self.client.get("/events/past/")

        self.assertContains(events_page, "Bring folders")
        self.assertContains(past_page, "Was moved to the hall")


class EditEventTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at2_the_edit_page_shows_the_current_values(self):
        event = make_event(date(2026, 11, 7), name="Concert", notes="Wear black")

        with fake_now(2026, 11, 1):
            response = self.client.get(f"/events/{event.pk}/edit/")

        self.assertContains(response, 'value="Concert"')
        self.assertContains(response, "Wear black")

    def test_at2_editing_changes_the_name_who_is_expected_and_the_notes(self):
        event = make_event(date(2026, 11, 7), name="Concert")

        with fake_now(2026, 11, 1):
            response = self.client.post(
                f"/events/{event.pk}/edit/", {"date": "2026-11-07", "name": "Winter concert", "expected": "praise_team", "notes": "Doors at 6"}
            )

        self.assertRedirects(response, "/events/")
        event.refresh_from_db()
        self.assertEqual((event.name, event.expected, event.notes), ("Winter concert", "praise_team", "Doors at 6"))

    def test_at2_editing_never_changes_the_kind(self):
        event = make_event(date(2026, 11, 7), name="Concert")

        with fake_now(2026, 11, 1):
            self.client.post(
                f"/events/{event.pk}/edit/",
                {"date": "2026-11-07", "kind": "extra", "name": "Concert", "expected": "everyone"},
            )

        event.refresh_from_db()
        self.assertEqual(event.kind, Event.Kind.SPECIAL)

    def test_at2_a_special_event_or_extra_rehearsal_can_have_its_date_corrected(self):
        special = make_event(date(2026, 11, 7), name="Concert")
        extra = make_event(date(2026, 11, 8), kind=Event.Kind.EXTRA, name="")

        with fake_now(2026, 11, 1):
            page = self.client.get(f"/events/{special.pk}/edit/")
            self.client.post(f"/events/{special.pk}/edit/", {"date": "2026-12-05", "name": "Concert", "expected": "everyone"})
            self.client.post(f"/events/{extra.pk}/edit/", {"date": "2026-12-02", "name": "", "expected": "everyone"})

        self.assertContains(page, 'name="date"')
        special.refresh_from_db()
        extra.refresh_from_db()
        self.assertEqual((special.date, extra.date), (date(2026, 12, 5), date(2026, 12, 2)))

    def test_at2_a_regular_events_date_cannot_be_changed(self):
        event = make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        with fake_now(2026, 11, 1):
            page = self.client.get(f"/events/{event.pk}/edit/")
            self.client.post(f"/events/{event.pk}/edit/", {"date": "2026-12-05", "expected": "everyone"})

        self.assertNotContains(page, 'name="date"')
        event.refresh_from_db()
        self.assertEqual(event.date, date(2026, 11, 7))

    def test_at2_a_regular_event_can_change_who_is_expected_and_its_notes_but_has_no_name(self):
        event = make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        with fake_now(2026, 11, 1):
            page = self.client.get(f"/events/{event.pk}/edit/")
            self.client.post(f"/events/{event.pk}/edit/", {"name": "Sneaky", "expected": "praise_team", "notes": "Sopranos only"})

        self.assertNotContains(page, 'name="name"')
        event.refresh_from_db()
        self.assertEqual((event.name, event.expected, event.notes), ("", "praise_team", "Sopranos only"))

    def test_at2_editing_keeps_the_name_rules(self):
        special = make_event(date(2026, 11, 7), name="Concert")
        extra = make_event(date(2026, 11, 8), kind=Event.Kind.EXTRA, name="Run-through")

        with fake_now(2026, 11, 1):
            no_name = self.client.post(
                f"/events/{special.pk}/edit/", {"date": "2026-11-07", "name": "", "expected": "everyone"}
            )
            cleared = self.client.post(
                f"/events/{extra.pk}/edit/", {"date": "2026-11-08", "name": "", "expected": "everyone"}
            )

        self.assertContains(no_name, "This field is required")
        special.refresh_from_db()
        self.assertEqual(special.name, "Concert")
        self.assertEqual(cleared.status_code, 302)
        extra.refresh_from_db()
        self.assertEqual(extra.name, "")

    def test_at2_a_failed_edit_still_names_the_event_as_it_is_saved(self):
        event = make_event(date(2026, 11, 7), name="Concert")

        with fake_now(2026, 11, 1):
            # A new name with an invalid "expected": the form fails, but it has already read the new name.
            response = self.client.post(f"/events/{event.pk}/edit/", {"date": "2026-11-07", "name": "Renamed", "expected": "nobody"})

        self.assertContains(response, "Concert on Sat, Nov 7, 2026")
        self.assertNotContains(response, "Renamed on")
        self.assertNotContains(response, "Special event on")

    def test_at2_a_canceled_upcoming_event_can_be_edited_and_stays_canceled(self):
        event = make_event(date(2026, 11, 7), name="Concert", canceled=True)

        with fake_now(2026, 11, 1):
            self.client.post(
                f"/events/{event.pk}/edit/", {"date": "2026-11-07", "name": "Concert", "expected": "everyone", "notes": "Moved"}
            )

        event.refresh_from_db()
        self.assertEqual(event.notes, "Moved")
        self.assertTrue(event.canceled)

    def test_at2_a_past_event_cannot_be_edited(self):
        event = make_event(date(2026, 10, 30), name="Earlier")

        with fake_now(2026, 11, 1):
            self.assertEqual(self.client.get(f"/events/{event.pk}/edit/").status_code, 404)
            self.assertEqual(self.client.post(f"/events/{event.pk}/edit/", {"name": "X", "expected": "everyone"}).status_code, 404)

        event.refresh_from_db()
        self.assertEqual(event.name, "Earlier")

    def test_at2_only_upcoming_rows_offer_edit(self):
        upcoming = make_event(date(2026, 11, 7), name="Upcoming")
        earlier = make_event(date(2026, 10, 30), name="Earlier")

        with fake_now(2026, 11, 1):
            events_page = self.client.get("/events/")
            past_page = self.client.get("/events/past/")

        self.assertContains(events_page, f'href="/events/{upcoming.pk}/edit/"')
        self.assertNotContains(past_page, f'href="/events/{earlier.pk}/edit/"')

    def test_at2_leaders_get_not_found_and_signed_out_visitors_go_to_sign_in(self):
        event = make_event(date(2026, 12, 5))
        self.client.logout()
        self.assertTrue(self.client.post(f"/events/{event.pk}/edit/")["Location"].startswith("/signin/"))

        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))
        self.assertEqual(self.client.get(f"/events/{event.pk}/edit/").status_code, 404)
        self.assertEqual(self.client.post(f"/events/{event.pk}/edit/", {"name": "X", "expected": "everyone"}).status_code, 404)


class EventAdminListTests(TestCase):
    def test_the_admin_event_list_does_not_repeat_the_kind_as_a_title(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        response = self.client.get("/admin/roster/event/")

        self.assertContains(response, "column-kind")
        self.assertContains(response, "column-name")
        self.assertNotContains(response, "column-title")


class DeleteEventTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_at2_the_confirm_page_names_the_event_warns_and_deletes_nothing(self):
        event = make_event(date(2026, 11, 7), name="Concert")

        with fake_now(2026, 11, 1):
            response = self.client.get(f"/events/{event.pk}/delete/")

        self.assertContains(response, "Delete Concert on Nov 7?")
        self.assertContains(response, "can't be undone")
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_at2_deleting_removes_a_special_event_and_an_extra_rehearsal(self):
        special = make_event(date(2026, 11, 7), name="Concert")
        extra = make_event(date(2026, 11, 8), kind=Event.Kind.EXTRA, name="")

        with fake_now(2026, 11, 1):
            response = self.client.post(f"/events/{special.pk}/delete/", follow=True)
            self.client.post(f"/events/{extra.pk}/delete/")

        self.assertRedirects(response, "/events/")
        self.assertContains(response, "Concert on Nov 7, 2026 is deleted.")
        self.assertFalse(Event.objects.exists())

    def test_at2_a_canceled_upcoming_event_can_be_deleted(self):
        event = make_event(date(2026, 11, 7), name="Concert", canceled=True)

        with fake_now(2026, 11, 1):
            self.client.post(f"/events/{event.pk}/delete/")

        self.assertFalse(Event.objects.exists())

    def test_at2_a_regular_event_cannot_be_deleted(self):
        event = make_event(date(2026, 11, 7), kind=Event.Kind.SATURDAY, name="")

        with fake_now(2026, 11, 1):
            self.assertEqual(self.client.get(f"/events/{event.pk}/delete/").status_code, 404)
            self.assertEqual(self.client.post(f"/events/{event.pk}/delete/").status_code, 404)

        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_at2_a_past_event_cannot_be_deleted(self):
        event = make_event(date(2026, 10, 30), name="Earlier")

        with fake_now(2026, 11, 1):
            self.assertEqual(self.client.get(f"/events/{event.pk}/delete/").status_code, 404)
            self.assertEqual(self.client.post(f"/events/{event.pk}/delete/").status_code, 404)

        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_at2_only_the_edit_page_of_a_special_or_extra_event_offers_delete(self):
        special = make_event(date(2026, 11, 7), name="Concert")
        regular = make_event(date(2026, 11, 8), kind=Event.Kind.SUNDAY, name="")

        with fake_now(2026, 11, 1):
            special_page = self.client.get(f"/events/{special.pk}/edit/")
            regular_page = self.client.get(f"/events/{regular.pk}/edit/")
            list_page = self.client.get("/events/")

        self.assertContains(special_page, f'href="/events/{special.pk}/delete/"')
        self.assertNotContains(regular_page, "/delete/")
        self.assertNotContains(list_page, "/delete/")

    def test_at2_leaders_get_not_found_and_signed_out_visitors_go_to_sign_in(self):
        event = make_event(date(2026, 12, 5))
        self.client.logout()
        self.assertTrue(self.client.post(f"/events/{event.pk}/delete/")["Location"].startswith("/signin/"))

        self.client.force_login(Account.objects.create_user("leader@example.com", sections=["alto"]))
        self.assertEqual(self.client.get(f"/events/{event.pk}/delete/").status_code, 404)
        self.assertEqual(self.client.post(f"/events/{event.pk}/delete/").status_code, 404)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())
