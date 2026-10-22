"""Tests for the deploy pipeline's one real page, the health check, and the static setup.

Everything goes through Django's test client, like a visitor or Railway would.
"""

import tempfile
from unittest import mock

from django.core.management import call_command
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings

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
    def test_admin_login_renders_with_unfold_styling(self):
        response = self.client.get("/admin/login/")

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
