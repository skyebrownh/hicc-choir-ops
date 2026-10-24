"""Members: adding, editing and viewing. Everything goes through the test client, signed in as a role."""

from django.test import TestCase

from accounts.models import Account
from roster.models import Member


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


class SignedOutTests(TestCase):
    def test_signed_out_visitors_are_sent_to_sign_in_from_every_member_page(self):
        member = Member.objects.create(name="Ada", section="bass")

        for url in ["/members/", "/members/new/", f"/members/{member.pk}/", f"/members/{member.pk}/edit/"]:
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
