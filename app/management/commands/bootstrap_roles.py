from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create BankRisk Compass roles and optionally bootstrap an administrator."

    def handle(self, *args, **options):
        groups = {
            name: Group.objects.get_or_create(name=name)[0]
            for name in ("Analysts", "Reviewers", "Administrators")
        }
        self.stdout.write(self.style.SUCCESS("Roles are ready."))

        username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip()
        if not username and not password:
            return
        if not username or not password:
            raise CommandError(
                "Set both BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD."
            )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            user.groups.add(groups["Administrators"])
            self.stdout.write(self.style.SUCCESS(f"Created administrator {username}."))
        else:
            self.stdout.write(f"Administrator {username} already exists; password unchanged.")
