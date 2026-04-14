from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser if one does not already exist."

    def handle(self, *args, **options):
        User = get_user_model()

        username = "vivekn"
        email = "nagarvivek23@gmail.com"
        password = "vivek@123"

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Superuser '{username}' already exists — skipping creation."
                )
            )
        else:
            User.objects.create_superuser(username, email, password)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Superuser '{username}' created successfully."
                )
            )
