"""Members: adding, editing and viewing. Everything goes through the test client, signed in as a role."""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Account
from roster.models import Member, StatusChange


def today():
    # Same clock the app uses (US Eastern), so tests agree with it near midnight UTC.
    return timezone.localdate()


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
                "section": "alto",
                "praise_team": "on",
                "notes": "Sings 2nd service only",
            },
        )

        member = Member.objects.get()
        self.assertRedirects(response, f"/members/{member.pk}/")
        detail = self.client.get(f"/members/{member.pk}/")
        for shown in ["Grace Hopper", "555-0100", "grace@example.com", "Alto", "Sings 2nd service only"]:
            self.assertContains(detail, shown)
        self.assertTrue(member.praise_team)

    def test_ro1_the_praise_team_label_shows_only_for_members_on_it(self):
        on = Member.objects.create(name="Ann On", section="alto", praise_team=True)
        off = Member.objects.create(name="Bob Off", section="bass", praise_team=False)

        for url, shown in [(f"/members/{on.pk}/", True), (f"/members/{off.pk}/", False)]:
            response = self.client.get(url)
            self.assertEqual(shown, "Praise Team</span>" in response.content.decode(), url)
        # The list marks the same member rows.
        self.assertContains(self.client.get("/members/"), "Praise Team</span>", count=1)

    def test_ro1_phone_and_email_can_be_blank(self):
        response = self.client.post("/members/new/", {"name": "Ada", "section": "bass"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Member.objects.get().phone, "")

    def test_ro1_a_missing_name_is_rejected(self):
        response = self.client.post("/members/new/", {"name": "", "section": "bass"})

        self.assertContains(response, "This field is required")
        self.assertFalse(Member.objects.exists())

    def test_ro1_a_malformed_email_is_rejected(self):
        response = self.client.post("/members/new/", {"name": "Ada", "section": "bass", "email": "not-an-email"})

        self.assertContains(response, "Enter a valid email address")
        self.assertFalse(Member.objects.exists())

    def test_ro3_admin_edits_a_member_and_the_changes_show(self):
        member = Member.objects.create(name="Ada", section="bass")

        response = self.client.post(
            f"/members/{member.pk}/edit/",
            {"name": "Ada Lovelace", "section": "tenor", "phone": "555-0111", "notes": "Moved up"},
        )

        self.assertRedirects(response, f"/members/{member.pk}/")
        detail = self.client.get(f"/members/{member.pk}/")
        for shown in ["Ada Lovelace", "Tenor", "555-0111", "Moved up"]:
            self.assertContains(detail, shown)

    def test_ro3_the_edit_page_starts_filled_in(self):
        member = Member.objects.create(name="Ada", section="bass")

        response = self.client.get(f"/members/{member.pk}/edit/")

        self.assertContains(response, 'value="Ada"')

    def test_ro3_admin_sees_every_member_in_the_list(self):
        Member.objects.create(name="Ada", section="bass")
        Member.objects.create(name="Grace", section="alto")

        response = self.client.get("/members/")

        self.assertContains(response, "Ada")
        self.assertContains(response, "Grace")

    def test_ro3_admin_opens_the_detail_page_of_a_member_in_any_section(self):
        for section in ["soprano", "alto", "tenor", "bass"]:
            member = Member.objects.create(name=f"Member {section}", section=section)

            response = self.client.get(f"/members/{member.pk}/")

            self.assertContains(response, f"Member {section}")


class SectionLeaderTests(TestCase):
    def setUp(self):
        self.alto = Member.objects.create(name="Alice Alto", section="alto")
        self.tenor = Member.objects.create(name="Tom Tenor", section="tenor")
        self.bass = Member.objects.create(name="Bea Bass", section="bass")
        self.soprano = Member.objects.create(name="Sue Soprano", section="soprano")
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
        self.client.post("/members/new/", {"name": "Sneaky", "section": "alto"})
        response = self.client.post(f"/members/{self.alto.pk}/edit/", {"name": "Renamed", "section": "alto"})

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
        self.alto = Member.objects.create(name="Alice Alto", section="alto")
        self.tenor = Member.objects.create(name="Tom Tenor", section="tenor")
        StatusChange.objects.create(member=self.alto, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.alto, status="on_break", effective_on=date(2026, 6, 1))
        self.client.force_login(Account.objects.create_user("alto@example.com", sections=["alto"]))

    def test_ro3_leader_sees_current_status_and_history_for_their_own_member(self):
        response = self.client.get(f"/members/{self.alto.pk}/")

        for shown in ["On Break", "Status history", "Jan 5, 2026", "Jun 1, 2026"]:
            self.assertContains(response, shown)

    def test_ro3_leader_gets_not_found_for_the_change_status_page_on_get_and_post(self):
        for member in [self.alto, self.tenor]:
            url = f"/members/{member.pk}/status/"
            self.assertEqual(self.client.get(url).status_code, 404, url)
            response = self.client.post(url, {"status": "inactive", "effective_on": today().isoformat()})
            self.assertEqual(response.status_code, 404, url)
        self.assertEqual(self.alto.current_status, "on_break")

    def test_ro3_leader_sees_no_change_status_control(self):
        self.assertNotContains(self.client.get(f"/members/{self.alto.pk}/"), "/status/")


class SignedOutTests(TestCase):
    def test_signed_out_visitors_are_sent_to_sign_in_from_every_member_page(self):
        member = Member.objects.create(name="Ada", section="bass")

        for url in ["/members/", "/members/new/", f"/members/{member.pk}/", f"/members/{member.pk}/edit/", f"/members/{member.pk}/status/"]:
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
        Member.objects.create(name="Grace Hopper", section="alto")

        response = self.client.get("/admin/roster/member/")

        self.assertContains(response, "Grace Hopper")


class StatusHistoryTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        self.member = Member.objects.create(name="Ada", section="bass")

    def test_ro2_detail_shows_the_current_status_and_history_newest_first(self):
        StatusChange.objects.create(member=self.member, status="active", effective_on=date(2026, 1, 5))
        StatusChange.objects.create(member=self.member, status="on_break", effective_on=date(2026, 6, 1))

        response = self.client.get(f"/members/{self.member.pk}/")

        self.assertEqual(self.member.current_status, "on_break")
        self.assertContains(response, "Status history")
        self.assertContains(response, "On Break")
        content = response.content.decode()
        self.assertLess(content.index("Jun 1, 2026"), content.index("Jan 5, 2026"))

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
        self.member = Member.objects.create(name="Ada", section="bass")
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


class InitialStatusTests(TestCase):
    def setUp(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))

    def test_ro2_a_new_member_defaults_to_active_dated_today(self):
        self.client.post("/members/new/", {"name": "Ada", "section": "bass", "initial_status": "active"})

        change = Member.objects.get().status_changes.get()
        self.assertEqual((change.status, change.effective_on), ("active", today()))

    def test_ro2_the_add_form_offers_status_with_active_selected(self):
        response = self.client.get("/members/new/")

        self.assertContains(response, "Status")
        self.assertContains(response, '<option value="active" selected>')

    def test_ro2_a_new_member_can_start_on_another_status(self):
        self.client.post("/members/new/", {"name": "Ada", "section": "bass", "initial_status": "on_break"})

        self.assertEqual(Member.objects.get().current_status, "on_break")

    def test_ro2_a_member_is_not_saved_when_the_initial_status_is_invalid(self):
        response = self.client.post("/members/new/", {"name": "Ada", "section": "bass", "initial_status": "retired"})

        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Member.objects.exists())

    def test_ro2_editing_a_member_does_not_add_a_status_change(self):
        member = Member.objects.create(name="Ada", section="bass")
        StatusChange.objects.create(member=member, status="on_break", effective_on=date(2026, 1, 5))

        response = self.client.post(f"/members/{member.pk}/edit/", {"name": "Ada L", "section": "bass"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(member.status_changes.count(), 1)
        self.assertNotContains(self.client.get(f"/members/{member.pk}/edit/"), "initial_status")


class BackfillMigrationTests(TestCase):
    def test_ro2_the_migration_gives_an_existing_member_an_active_status_dated_that_day(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module("roster.migrations.0002_statuschange")
        lonely = Member.objects.create(name="Had no status", section="alto")
        keeps = Member.objects.create(name="Already set", section="bass")
        StatusChange.objects.create(member=keeps, status="inactive", effective_on=date(2026, 1, 5))

        migration.give_existing_members_an_active_status(apps, None)

        change = lonely.status_changes.get()
        self.assertEqual((change.status, change.effective_on), ("active", today()))
        # A member who already has a status is left alone.
        self.assertEqual(keeps.current_status, "inactive")
        self.assertEqual(keeps.status_changes.count(), 1)


class StatusAdminTests(TestCase):
    def test_ro2_admin_sees_a_members_status_changes_in_the_django_admin(self):
        self.client.force_login(Account.objects.create_superuser("admin@example.com"))
        member = Member.objects.create(name="Grace Hopper", section="alto")
        StatusChange.objects.create(member=member, status="on_break", effective_on=date(2026, 6, 1))

        response = self.client.get(f"/admin/roster/member/{member.pk}/change/")

        self.assertContains(response, "2026-06-01")
        self.assertContains(response, 'value="on_break" selected')
