from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Section(models.TextChoices):
    SOPRANO = "soprano", "Soprano"
    ALTO = "alto", "Alto"
    TENOR = "tenor", "Tenor"
    BASS = "bass", "Bass"


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    SECTION_LEADER = "section_leader", "Section leader"


class AccountManager(BaseUserManager):
    def create_user(self, email, role=Role.SECTION_LEADER, **extra):
        # AC-1: there are no passwords, so nobody can sign in by one.
        account = self.model(email=self.normalize_email(email), role=role, **extra)
        account.set_unusable_password()
        account.save(using=self._db)
        return account

    def create_superuser(self, email, **extra):
        # `createsuperuser` makes an Admin; the role is the only privilege we store.
        return self.create_user(email, role=Role.ADMIN, **extra)


class Account(AbstractBaseUser):
    """A person who can sign in (SPEC.md, Account). Sign-in is by emailed code, never a password."""

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    # Section leaders only; one or more. The link to a member is added with the account pages (#13).
    sections = ArrayField(
        models.CharField(max_length=10, choices=Section.choices),
        default=list,
        blank=True,
    )

    USERNAME_FIELD = "email"
    objects = AccountManager()

    class Meta:
        constraints = [
            # Sign-in matches emails ignoring case, so two spellings of one address
            # would make the lookup ambiguous.
            models.UniqueConstraint(Lower("email"), name="account_email_unique_ignoring_case"),
        ]

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    # The next few exist only because Django's admin and permission checks ask for
    # them. Our own code asks `is_admin`; the role is the one thing we store.
    @property
    def is_staff(self):
        return self.is_admin

    @property
    def is_superuser(self):
        return self.is_admin

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return self.is_admin


class SignInCode(models.Model):
    """A one-time code emailed to an account (SPEC.md, Sign-in code). Stored hashed."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    code = models.CharField(max_length=128)  # make_password hash, never the digits
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)


class SignInRequest(models.Model):
    """One allowed request for a sign-in code (AC-7). Counted to enforce the hourly limits.

    Kept in Postgres rather than Django's cache: the cache is per process and
    gunicorn runs several workers, so each would count separately.
    """

    email = models.EmailField()  # stored lowercased, so spellings share one limit
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["email", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
        ]
